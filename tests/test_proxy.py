import asyncio

import httpx
from fastapi.testclient import TestClient

from poolswitch.config import AppConfig, KeyConfig
from poolswitch.proxy.app import create_app


def test_proxy_fails_over_after_quota_error() -> None:
    config = AppConfig(
        upstream_base_url="https://upstream.example",
        strategy="quota_failover",
        retry_attempts=3,
        cooldown_seconds=600,
        keys=[
            KeyConfig(id="primary", value="sk-primary"),
            KeyConfig(id="secondary", value="sk-secondary"),
        ],
    )
    app = create_app(config)
    seen_auth_headers: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_auth_headers.append(request.headers["Authorization"])
        if len(seen_auth_headers) == 1:
            return httpx.Response(
                429,
                headers={"content-type": "application/json"},
                json={"error": {"message": "quota exceeded"}},
            )
        return httpx.Response(
            200,
            headers={"content-type": "application/json", "x-ratelimit-remaining": "41"},
            json={"ok": True},
        )

    transport = httpx.MockTransport(handler)

    with TestClient(app) as client:
        original_client = app.state.proxy_service.client
        app.state.proxy_service.client = httpx.AsyncClient(transport=transport)
        try:
            response = client.post("/v1/chat/completions", json={"model": "demo"})
            assert response.status_code == 200
            assert response.json() == {"ok": True}
            assert seen_auth_headers == ["Bearer sk-primary", "Bearer sk-secondary"]

            status = client.get("/status")
            assert status.status_code == 200
            payload = status.json()
            primary = next(item for item in payload["keys"] if item["id"] == "primary")
            secondary = next(item for item in payload["keys"] if item["id"] == "secondary")
            assert primary["cooldown_until"] is not None
            assert secondary["total_requests"] == 1
        finally:
            asyncio.run(app.state.proxy_service.client.aclose())
            app.state.proxy_service.client = original_client

