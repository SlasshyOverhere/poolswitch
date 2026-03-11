from __future__ import annotations

import asyncio
import time
from collections import deque
from itertools import chain, repeat

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from poolswitch.config import AppConfig, KeyConfig
from poolswitch.core.key_pool import KeyPool
from poolswitch.metrics import Metrics
from poolswitch.models import APIKeyDefinition, APIKeyState, KeyRecord
from poolswitch.proxy.app import AsyncRateLimiter, ProxyService, create_app
from poolswitch.storage.memory import InMemoryKeyStateStore
from poolswitch.strategies.impl import RoundRobinStrategy


def _config(**overrides):
    base = dict(
        upstream_base_url="https://upstream.example",
        keys=[KeyConfig(id="primary", value="sk-primary"), KeyConfig(id="secondary", value="sk-secondary")],
        retry_attempts=1,
        rate_limit_per_second=1000.0,
    )
    base.update(overrides)
    return AppConfig(**base)


def _key_record(key_id: str, value: str = "sk") -> KeyRecord:
    return KeyRecord(definition=APIKeyDefinition(id=key_id, value=value), state=APIKeyState(key_id=key_id))


def _make_request(headers: dict[str, str] | None = None) -> Request:
    raw_headers = [(k.encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": raw_headers,
        "query_string": b"",
        "client": ("127.0.0.1", 1234),
        "server": ("127.0.0.1", 8080),
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_outbound_headers_auth_and_hop_by_hop() -> None:
    config = _config(auth_scheme=None, auth_header_name="Authorization")
    pool = KeyPool(config, [], InMemoryKeyStateStore(), RoundRobinStrategy(), Metrics())
    service = ProxyService(config=config, metrics=Metrics(), pool=pool, client=httpx.AsyncClient())

    request = _make_request(
        {
            "authorization": "Bearer should-drop",
            "connection": "keep-alive",
            "content-length": "10",
            "x-custom": "ok",
        }
    )
    headers = service._outbound_headers(request, _key_record("demo", "sk-demo"))

    assert "connection" not in headers
    assert "content-length" not in headers
    assert headers["Authorization"] == "sk-demo"
    assert headers["x-custom"] == "ok"
    assert headers["x-poolswitch-key-id"] == "demo"

    await service.client.aclose()


@pytest.mark.asyncio
async def test_outbound_headers_strip_connection_named_headers() -> None:
    config = _config(auth_scheme=None, auth_header_name="Authorization")
    pool = KeyPool(config, [], InMemoryKeyStateStore(), RoundRobinStrategy(), Metrics())
    service = ProxyService(config=config, metrics=Metrics(), pool=pool, client=httpx.AsyncClient())

    request = _make_request(
        {
            "connection": "x-remove-me, , keep-alive",
            "x-remove-me": "bye",
            "x-custom": "ok",
        }
    )
    headers = service._outbound_headers(request, _key_record("demo", "sk-demo"))

    assert "x-remove-me" not in headers
    assert headers["x-custom"] == "ok"

    await service.client.aclose()


def test_response_headers_filtering() -> None:
    headers = httpx.Headers({"connection": "keep-alive", "x-demo": "1"})
    filtered = ProxyService._response_headers(headers)
    assert "connection" not in filtered
    assert filtered["x-demo"] == "1"


def test_extract_remaining_quota_from_headers() -> None:
    response = httpx.Response(200, headers={"x-ratelimit-remaining": "10.5"}, content=b"ok")
    assert ProxyService._extract_remaining_quota(response) == 10

    response = httpx.Response(
        200,
        headers={"x-ratelimit-remaining": "not-a-number", "content-type": "application/json"},
        json={"usage": {"remaining_quota": 3}},
    )
    assert ProxyService._extract_remaining_quota(response) == 3


def test_extract_remaining_quota_from_json() -> None:
    response = httpx.Response(
        200,
        headers={"content-type": "application/json"},
        json={"usage": {"remaining_quota": 7}},
    )
    assert ProxyService._extract_remaining_quota(response) == 7


def test_extract_remaining_quota_invalid_json() -> None:
    response = httpx.Response(200, headers={"content-type": "application/json"}, content=b"{bad json")
    assert ProxyService._extract_remaining_quota(response) is None


def test_extract_remaining_quota_non_int() -> None:
    response = httpx.Response(
        200,
        headers={"content-type": "application/json"},
        json={"usage": {"remaining_quota": "soon"}},
    )
    assert ProxyService._extract_remaining_quota(response) is None


@pytest.mark.asyncio
async def test_rate_limiter_sleeps(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter = AsyncRateLimiter(requests_per_second=1)
    limiter._timestamps = deque([0.0, 1.2])
    calls = chain([2.0, 3.2, 3.2], repeat(3.2))
    slept: list[float] = []

    monkeypatch.setattr(time, "monotonic", lambda: next(calls))

    async def fake_sleep(delay: float) -> None:
        slept.append(delay)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    await limiter.acquire()
    await limiter.acquire()

    assert slept


def test_proxy_rejects_internal_post() -> None:
    config = _config()
    app = create_app(config)

    with TestClient(app) as client:
        response = client.post("/metrics")
        assert response.status_code == 404


def test_healthz_and_metrics_routes() -> None:
    config = _config()
    app = create_app(config)

    with TestClient(app) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}

        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        assert "poolswitch_requests_total" in metrics.text


def test_proxy_network_error_non_retryable() -> None:
    config = _config(retry_attempts=1)
    app = create_app(config)

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    transport = httpx.MockTransport(handler)

    with TestClient(app) as client:
        original_client = app.state.proxy_service.client
        app.state.proxy_service.client = httpx.AsyncClient(transport=transport)
        try:
            response = client.patch("/v1/demo", json={"ok": True})
            assert response.status_code == 502
        finally:
            asyncio.run(app.state.proxy_service.client.aclose())
            app.state.proxy_service.client = original_client


def test_proxy_network_error_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _config(retry_attempts=2)
    app = create_app(config)
    calls = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)

    with TestClient(app) as client:
        original_client = app.state.proxy_service.client
        app.state.proxy_service.client = httpx.AsyncClient(transport=transport)

        async def no_sleep(_decision):
            return None

        monkeypatch.setattr(app.state.proxy_service.retry_policy, "sleep", no_sleep)

        try:
            response = client.get("/v1/demo")
            assert response.status_code == 200
        finally:
            asyncio.run(app.state.proxy_service.client.aclose())
            app.state.proxy_service.client = original_client


def test_proxy_rate_limit_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _config(retry_attempts=2)
    app = create_app(config)
    calls = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(
                429,
                headers={"content-type": "application/json"},
                json={"error": {"message": "Slow down"}},
            )
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)

    with TestClient(app) as client:
        original_client = app.state.proxy_service.client
        app.state.proxy_service.client = httpx.AsyncClient(transport=transport)
        app.state.proxy_service.retry_policy.attempts = 2

        async def no_sleep(_decision):
            return None

        monkeypatch.setattr(app.state.proxy_service.retry_policy, "sleep", no_sleep)

        try:
            response = client.get("/v1/demo")
            assert response.status_code == 200
            assert response.json() == {"ok": True}
        finally:
            asyncio.run(app.state.proxy_service.client.aclose())
            app.state.proxy_service.client = original_client


def test_proxy_quota_exceeded_no_retry() -> None:
    config = _config(retry_attempts=1)
    app = create_app(config)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={"content-type": "application/json"},
            json={"error": {"message": "quota exceeded"}},
        )

    transport = httpx.MockTransport(handler)

    with TestClient(app) as client:
        original_client = app.state.proxy_service.client
        app.state.proxy_service.client = httpx.AsyncClient(transport=transport)
        try:
            response = client.post("/v1/demo", json={"ok": True})
            assert response.status_code == 429
        finally:
            asyncio.run(app.state.proxy_service.client.aclose())
            app.state.proxy_service.client = original_client


def test_proxy_rate_limit_no_retry() -> None:
    config = _config(retry_attempts=1)
    app = create_app(config)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={"content-type": "application/json"},
            json={"error": {"message": "Slow down"}},
        )

    transport = httpx.MockTransport(handler)

    with TestClient(app) as client:
        original_client = app.state.proxy_service.client
        app.state.proxy_service.client = httpx.AsyncClient(transport=transport)
        try:
            response = client.get("/v1/demo")
            assert response.status_code == 429
        finally:
            asyncio.run(app.state.proxy_service.client.aclose())
            app.state.proxy_service.client = original_client


def test_proxy_no_healthy_keys() -> None:
    config = _config()
    app = create_app(config)

    with TestClient(app) as client:
        asyncio.run(app.state.pool.mark_key_quota_exhausted("primary", "quota_exceeded"))
        asyncio.run(app.state.pool.mark_key_quota_exhausted("secondary", "quota_exceeded"))
        response = client.get("/v1/demo")
        assert response.status_code == 503


