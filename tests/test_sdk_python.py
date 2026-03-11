from __future__ import annotations

import httpx
import pytest

from poolswitch_client import PoolSwitchClient, PoolSwitchError


def test_client_strips_trailing_slash() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True}))
    client = PoolSwitchClient(
        "https://example.com/",
        client=httpx.Client(base_url="https://example.com", transport=transport),
    )
    result = client.get("/v1/demo")
    assert result == {"ok": True}


def test_client_returns_text() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text="hello"))
    client = PoolSwitchClient(
        "https://example.com",
        client=httpx.Client(base_url="https://example.com", transport=transport),
    )
    result = client.get("/v1/demo")
    assert result == "hello"


def test_client_raises_error() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(400, text="bad"))
    client = PoolSwitchClient(
        "https://example.com",
        client=httpx.Client(base_url="https://example.com", transport=transport),
    )
    with pytest.raises(PoolSwitchError) as exc:
        client.get("/v1/demo")
    assert "400" in str(exc.value)


def test_client_post_wrapper() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True}))
    client = PoolSwitchClient(
        "https://example.com",
        client=httpx.Client(base_url="https://example.com", transport=transport),
    )
    assert client.post("/v1/demo", json={"x": 1}) == {"ok": True}


def test_client_context_manager_closes() -> None:
    closed = {"flag": False}

    class DummyClient(httpx.Client):
        def close(self) -> None:
            closed["flag"] = True
            super().close()

    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True}))
    dummy = DummyClient(base_url="https://example.com", transport=transport)

    with PoolSwitchClient("https://example.com", client=dummy) as client:
        client.get("/v1/demo")

    assert closed["flag"] is True


def test_error_string() -> None:
    error = PoolSwitchError(status_code=500, response_text="boom")
    assert "500" in str(error)


