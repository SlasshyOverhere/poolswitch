from __future__ import annotations

import httpx
import pytest

from poolswitch.core.quota import _flatten_messages, classify_response, response_payload


@pytest.mark.asyncio
async def test_response_payload_non_json() -> None:
    response = httpx.Response(200, headers={"content-type": "text/plain"}, content=b"hi")
    assert await response_payload(response) is None


@pytest.mark.asyncio
async def test_response_payload_invalid_json() -> None:
    response = httpx.Response(200, headers={"content-type": "application/json"}, content=b"not-json")
    assert await response_payload(response) is None


def test_flatten_messages() -> None:
    payload = {"error": {"message": ["Quota", "Exceeded"]}}
    assert "quota" in _flatten_messages(payload)


@pytest.mark.asyncio
async def test_classify_quota_exceeded_429() -> None:
    response = httpx.Response(
        429,
        headers={"content-type": "application/json"},
        json={"error": {"message": "Quota exceeded"}},
    )
    should_retry, quota_exceeded, reason = await classify_response(response)
    assert should_retry is True
    assert quota_exceeded is True
    assert reason == "quota_exceeded"


@pytest.mark.asyncio
async def test_classify_rate_limited_429() -> None:
    response = httpx.Response(
        429,
        headers={"content-type": "application/json"},
        json={"error": {"message": "Slow down"}},
    )
    should_retry, quota_exceeded, reason = await classify_response(response)
    assert should_retry is True
    assert quota_exceeded is False
    assert reason == "rate_limited"


@pytest.mark.asyncio
async def test_classify_quota_exceeded_401() -> None:
    response = httpx.Response(
        401,
        headers={"content-type": "application/json"},
        json={"error": {"message": "insufficient_quota"}},
    )
    should_retry, quota_exceeded, reason = await classify_response(response)
    assert should_retry is False
    assert quota_exceeded is True
    assert reason == "quota_exceeded"


@pytest.mark.asyncio
async def test_classify_retry_after_500() -> None:
    response = httpx.Response(500, headers={"retry-after": "1"}, content=b"boom")
    should_retry, quota_exceeded, reason = await classify_response(response)
    assert should_retry is True
    assert quota_exceeded is False
    assert reason == "upstream_retry_after"


@pytest.mark.asyncio
async def test_classify_ok() -> None:
    response = httpx.Response(200, content=b"ok")
    should_retry, quota_exceeded, reason = await classify_response(response)
    assert should_retry is False
    assert quota_exceeded is False
    assert reason == "ok"

