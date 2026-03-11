from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from poolswitch import AsyncPoolSwitchClient, PoolSwitchClient, PoolSwitchError
from poolswitch.client import _build_client_config, _coerce_key_config, _coerce_storage_config
from poolswitch.config import KeyConfig, StorageConfig
from poolswitch.models import APIKeyDefinition


def _factory_from_handler(handler):
    def factory(timeout: httpx.Timeout) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=timeout)

    return factory


def test_coerce_key_config_variants() -> None:
    key_config = KeyConfig(id="primary", value="sk-primary")
    assert _coerce_key_config(key_config, index=1) is key_config

    definition = APIKeyDefinition(id="secondary", value="sk-secondary", monthly_quota=50, metadata={"tier": "free"})
    converted = _coerce_key_config(definition, index=2)
    assert converted.id == "secondary"
    assert converted.monthly_quota == 50
    assert converted.metadata == {"tier": "free"}

    generated = _coerce_key_config("sk-third", index=3)
    assert generated.id == "key-3"
    assert generated.value == "sk-third"

    mapped = _coerce_key_config({"id": "mapped", "value": "sk-mapped"}, index=4)
    assert mapped.id == "mapped"


def test_coerce_key_config_rejects_invalid_type() -> None:
    with pytest.raises(TypeError):
        _coerce_key_config(123, index=1)  # type: ignore[arg-type]


def test_coerce_storage_config_variants() -> None:
    default_storage = _coerce_storage_config(None)
    assert default_storage.backend == "memory"

    configured = StorageConfig(backend="sqlite", sqlite_path="state.db")
    assert _coerce_storage_config(configured) is configured

    mapped = _coerce_storage_config({"backend": "redis", "redis_url": "redis://example"})
    assert mapped.backend == "redis"
    assert mapped.redis_url == "redis://example"


def test_build_client_config_defaults_retryable_methods() -> None:
    config = _build_client_config(
        upstream_base_url="https://api.example.com",
        keys=["sk-primary"],
        auth_header_name="Authorization",
        auth_scheme="Bearer",
        strategy="quota_failover",
        retry_attempts=3,
        cooldown_seconds=60,
        request_timeout_seconds=10.0,
        connect_timeout_seconds=5.0,
        rate_limit_per_second=25.0,
        retryable_methods=None,
        storage=None,
    )
    assert config.retryable_methods == ["GET", "HEAD", "OPTIONS", "DELETE", "POST"]


def test_poolswitch_error_string_variants() -> None:
    bare = PoolSwitchError("boom")
    assert str(bare) == "boom"

    detailed = PoolSwitchError("failed", status_code=429, reason="rate_limited", response_text="slow down")
    assert "status=429" in str(detailed)
    assert "reason=rate_limited" in str(detailed)
    assert "slow down" in str(detailed)


@pytest.mark.asyncio
async def test_async_client_json_success_and_status() -> None:
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.headers))
        return httpx.Response(
            200,
            headers={"content-type": "application/json", "x-ratelimit-remaining": "9"},
            json={"ok": True},
        )

    async with AsyncPoolSwitchClient(
        upstream_base_url="https://api.example.com",
        keys=["sk-primary"],
        headers={"x-default": "yes", "Authorization": "override-me"},
        client_factory=_factory_from_handler(handler),
    ) as client:
        result = await client.post("/v1/search", json={"q": "hello"}, headers={"x-request": "1"})
        status = await client.status()

    assert result == {"ok": True}
    assert seen[0]["authorization"] == "Bearer sk-primary"
    assert seen[0]["x-default"] == "yes"
    assert seen[0]["x-request"] == "1"
    assert status["keys"][0]["estimated_remaining_quota"] == 9
    assert status["keys"][0]["total_requests"] == 1


@pytest.mark.asyncio
async def test_async_client_text_success_and_auth_without_scheme() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Api-Key"] == "sk-plain"
        return httpx.Response(200, text="hello")

    client = AsyncPoolSwitchClient(
        upstream_base_url="https://api.example.com/base",
        keys=[{"id": "plain", "value": "sk-plain"}],
        auth_header_name="X-Api-Key",
        auth_scheme=None,
        client_factory=_factory_from_handler(handler),
    )

    assert await client.get("v1/ping") == "hello"
    await client.aclose()


@pytest.mark.asyncio
async def test_async_client_network_retry_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, headers={"content-type": "application/json"}, json={"ok": True})

    client = AsyncPoolSwitchClient(
        upstream_base_url="https://api.example.com",
        keys=["sk-primary", "sk-secondary"],
        retry_attempts=2,
        client_factory=_factory_from_handler(handler),
    )
    sleeps: list[float] = []

    async def fake_sleep(decision) -> None:
        sleeps.append(decision.delay_seconds)

    monkeypatch.setattr(client.retry_policy, "sleep", fake_sleep)

    assert await client.get("/v1/search") == {"ok": True}
    assert sleeps
    await client.aclose()


@pytest.mark.asyncio
async def test_async_client_network_error_raises_without_retry() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    client = AsyncPoolSwitchClient(
        upstream_base_url="https://api.example.com",
        keys=["sk-primary"],
        retry_attempts=1,
        client_factory=_factory_from_handler(handler),
    )

    with pytest.raises(PoolSwitchError) as exc:
        await client.patch("/v1/search", json={"q": "hello"})

    assert exc.value.reason == "network_error"
    assert exc.value.cause is not None
    await client.aclose()


@pytest.mark.asyncio
async def test_async_client_quota_failover_between_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    auth_headers: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        auth_headers.append(request.headers["Authorization"])
        if len(auth_headers) == 1:
            return httpx.Response(
                429,
                headers={"content-type": "application/json"},
                json={"error": {"message": "quota exceeded"}},
            )
        return httpx.Response(200, headers={"content-type": "application/json"}, json={"ok": True})

    client = AsyncPoolSwitchClient(
        upstream_base_url="https://api.example.com",
        keys=["sk-primary", "sk-secondary"],
        retry_attempts=3,
        client_factory=_factory_from_handler(handler),
    )

    async def no_sleep(_decision) -> None:
        return None

    monkeypatch.setattr(client.retry_policy, "sleep", no_sleep)

    assert await client.post("/v1/search", json={"q": "hello"}) == {"ok": True}
    status = await client.status()
    first = next(item for item in status["keys"] if item["id"] == "key-1")
    second = next(item for item in status["keys"] if item["id"] == "key-2")

    assert auth_headers == ["Bearer sk-primary", "Bearer sk-secondary"]
    assert first["cooldown_until"] is not None
    assert second["total_requests"] == 1
    await client.aclose()


@pytest.mark.asyncio
async def test_async_client_rate_limit_raises_when_retries_exhausted() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={"content-type": "application/json"},
            json={"error": {"message": "Slow down"}},
        )

    client = AsyncPoolSwitchClient(
        upstream_base_url="https://api.example.com",
        keys=["sk-primary"],
        retry_attempts=1,
        client_factory=_factory_from_handler(handler),
    )

    with pytest.raises(PoolSwitchError) as exc:
        await client.get("/v1/search")

    assert exc.value.status_code == 429
    assert exc.value.reason == "rate_limited"
    await client.aclose()


@pytest.mark.asyncio
async def test_async_client_rate_limit_retry_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(
                429,
                headers={"content-type": "application/json"},
                json={"error": {"message": "Slow down"}},
            )
        return httpx.Response(200, headers={"content-type": "application/json"}, json={"ok": True})

    client = AsyncPoolSwitchClient(
        upstream_base_url="https://api.example.com",
        keys=["sk-primary", "sk-secondary"],
        retry_attempts=2,
        client_factory=_factory_from_handler(handler),
    )

    async def no_sleep(_decision) -> None:
        return None

    monkeypatch.setattr(client.retry_policy, "sleep", no_sleep)

    assert await client.get("/v1/search") == {"ok": True}
    await client.aclose()


@pytest.mark.asyncio
async def test_async_client_quota_error_raises_when_retries_exhausted() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={"content-type": "application/json"},
            json={"error": {"message": "quota exceeded"}},
        )

    client = AsyncPoolSwitchClient(
        upstream_base_url="https://api.example.com",
        keys=["sk-primary"],
        retry_attempts=1,
        client_factory=_factory_from_handler(handler),
    )

    with pytest.raises(PoolSwitchError) as exc:
        await client.post("/v1/search", json={"q": "hello"})

    assert exc.value.status_code == 429
    assert exc.value.reason == "quota_exceeded"
    await client.aclose()


@pytest.mark.asyncio
async def test_async_client_non_retryable_error_increments_state() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="bad request")

    client = AsyncPoolSwitchClient(
        upstream_base_url="https://api.example.com",
        keys=["sk-primary"],
        client_factory=_factory_from_handler(handler),
    )

    with pytest.raises(PoolSwitchError) as exc:
        await client.get("/v1/search")

    assert exc.value.status_code == 400
    status = await client.status()
    assert status["keys"][0]["total_requests"] == 1
    await client.aclose()


@pytest.mark.asyncio
async def test_async_client_ensure_ready_short_circuits_inside_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeLock:
        async def __aenter__(self) -> None:
            client._pool = AsyncMock()

        async def __aexit__(self, *_args: Any) -> None:
            return None

    build_pool = AsyncMock()
    monkeypatch.setattr("poolswitch.client.build_key_pool", build_pool)

    client = AsyncPoolSwitchClient(upstream_base_url="https://api.example.com", keys=["sk-primary"])
    client._setup_lock = FakeLock()  # type: ignore[assignment]
    await client._ensure_ready()

    build_pool.assert_not_awaited()
    await client.aclose()


@pytest.mark.asyncio
async def test_async_client_surfaces_no_healthy_keys() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={"content-type": "application/json"},
            json={"error": {"message": "quota exceeded"}},
        )

    client = AsyncPoolSwitchClient(
        upstream_base_url="https://api.example.com",
        keys=["sk-primary"],
        retry_attempts=2,
        client_factory=_factory_from_handler(handler),
    )

    with pytest.raises(PoolSwitchError) as exc:
        await client.post("/v1/search", json={"q": "hello"})

    assert exc.value.reason == "no_healthy_keys"
    await client.aclose()


@pytest.mark.asyncio
async def test_async_client_aclose_closes_redis_and_rejects_new_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[httpx.Timeout] = []

    class FakeRedis:
        def __init__(self) -> None:
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

    def factory(timeout: httpx.Timeout) -> httpx.AsyncClient:
        created.append(timeout)
        return httpx.AsyncClient(transport=httpx.MockTransport(lambda _request: httpx.Response(200, text="ok")), timeout=timeout)

    fake_builder = AsyncMock()
    fake_pool = AsyncMock()
    fake_pool.list_records = AsyncMock(return_value=[])
    fake_pool.state_store.redis = FakeRedis()
    fake_builder.return_value = fake_pool
    monkeypatch.setattr("poolswitch.client.build_key_pool", fake_builder)

    client = AsyncPoolSwitchClient(
        upstream_base_url="https://api.example.com",
        keys=["sk-primary"],
        client_factory=factory,
    )

    await client.status()
    await client.aclose()

    assert created
    assert fake_pool.state_store.redis.closed is True
    with pytest.raises(RuntimeError):
        await client.get("/v1/search")


@pytest.mark.asyncio
async def test_async_client_aclose_is_idempotent_and_safe_before_start() -> None:
    client = AsyncPoolSwitchClient(upstream_base_url="https://api.example.com", keys=["sk-primary"])
    await client.aclose()
    await client.aclose()


@pytest.mark.asyncio
async def test_async_client_default_httpx_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[httpx.Timeout] = []

    class FakeClient:
        def __init__(self, *, timeout: httpx.Timeout) -> None:
            created.append(timeout)

        async def request(self, **_kwargs: Any) -> httpx.Response:
            return httpx.Response(200, headers={"content-type": "application/json"}, json={"ok": True})

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr("poolswitch.client.httpx.AsyncClient", FakeClient)
    client = AsyncPoolSwitchClient(upstream_base_url="https://api.example.com", keys=["sk-primary"])

    assert await client.get("/v1/search") == {"ok": True}
    assert created
    await client.aclose()


@pytest.mark.asyncio
async def test_async_client_uses_provided_client_without_closing_it() -> None:
    closed = {"flag": False}

    class ProvidedClient(httpx.AsyncClient):
        async def aclose(self) -> None:
            closed["flag"] = True
            await super().aclose()

    provided = ProvidedClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, text="ok")),
        timeout=httpx.Timeout(5.0),
    )
    client = AsyncPoolSwitchClient(
        upstream_base_url="https://api.example.com",
        keys=["sk-primary"],
        client=provided,
    )

    assert await client.get("/v1/search") == "ok"
    await client.aclose()

    assert closed["flag"] is False
    await provided.aclose()


@pytest.mark.asyncio
async def test_async_client_put_and_delete_wrappers(monkeypatch: pytest.MonkeyPatch) -> None:
    client = AsyncPoolSwitchClient(
        upstream_base_url="https://api.example.com",
        keys=["sk-primary"],
        client_factory=_factory_from_handler(lambda _request: httpx.Response(200, text="unused")),
    )
    calls: list[tuple[str, str]] = []

    async def fake_request(method: str, path: str, **_kwargs: Any) -> str:
        calls.append((method, path))
        return method

    monkeypatch.setattr(client, "request", fake_request)

    assert await client.put("/put") == "PUT"
    assert await client.delete("/delete") == "DELETE"
    await client.aclose()

    assert calls == [("PUT", "/put"), ("DELETE", "/delete")]


def test_sync_client_success_and_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/search":
            return httpx.Response(200, headers={"content-type": "application/json"}, json={"ok": True})
        raise AssertionError(request.url.path)

    with PoolSwitchClient(
        upstream_base_url="https://api.example.com",
        keys=["sk-primary"],
        client_factory=_factory_from_handler(handler),
    ) as client:
        assert client.get("/v1/search") == {"ok": True}
        status = client.status()

    assert status["keys"][0]["total_requests"] == 1


def test_sync_client_request_wrappers_and_close_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[tuple[str, str]] = []

    async def fake_request(method: str, path: str, **_kwargs: Any) -> str:
        called.append((method, path))
        return method

    async def fake_status() -> dict[str, str]:
        return {"ok": "yes"}

    async def fake_close() -> None:
        return None

    client = PoolSwitchClient(
        upstream_base_url="https://api.example.com",
        keys=["sk-primary"],
        client_factory=_factory_from_handler(lambda _request: httpx.Response(200, text="unused")),
    )
    monkeypatch.setattr(client._client, "request", fake_request)
    monkeypatch.setattr(client._client, "status", fake_status)
    monkeypatch.setattr(client._client, "aclose", fake_close)

    assert client.post("/one") == "POST"
    assert client.put("/two") == "PUT"
    assert client.patch("/three") == "PATCH"
    assert client.delete("/four") == "DELETE"
    assert client.status() == {"ok": "yes"}

    client.close()
    client.close()

    assert called == [("POST", "/one"), ("PUT", "/two"), ("PATCH", "/three"), ("DELETE", "/four")]
    with pytest.raises(RuntimeError):
        client.get("/after-close")

    coroutine = asyncio.sleep(0)
    try:
        with pytest.raises(RuntimeError):
            client._submit(coroutine)
    finally:
        coroutine.close()

    with pytest.raises(RuntimeError):
        client.status()


def test_sync_client_close_cancels_pending_tasks() -> None:
    client = PoolSwitchClient(
        upstream_base_url="https://api.example.com",
        keys=["sk-primary"],
        client_factory=_factory_from_handler(lambda _request: httpx.Response(200, text="ok")),
    )
    pending = asyncio.run_coroutine_threadsafe(asyncio.sleep(10), client._loop)

    client.close()

    assert pending.cancelled() or pending.done()
