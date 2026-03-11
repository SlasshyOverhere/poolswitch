from __future__ import annotations

from typing import Any

import httpx


QUOTA_HINTS = (
    "quota",
    "insufficient_quota",
    "quota_exceeded",
    "credits exhausted",
)

RATE_LIMIT_HINTS = (
    "rate limit",
    "too many requests",
    "slow down",
    "throttled",
)


async def response_payload(response: httpx.Response) -> dict[str, Any] | None:
    content_type = response.headers.get("content-type", "")
    if "application/json" not in content_type.lower():
        return None
    try:
        return response.json()
    except ValueError:
        return None


def _flatten_messages(payload: Any) -> str:
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload.lower()
    if isinstance(payload, dict):
        return " ".join(_flatten_messages(value) for value in payload.values())
    if isinstance(payload, list):
        return " ".join(_flatten_messages(item) for item in payload)
    return str(payload).lower()


async def classify_response(response: httpx.Response) -> tuple[bool, bool, str]:
    payload = await response_payload(response)
    message_blob = _flatten_messages(payload)
    retry_after = response.headers.get("retry-after")

    if response.status_code == 429:
        if any(hint in message_blob for hint in QUOTA_HINTS):
            return True, True, "quota_exceeded"
        if any(hint in message_blob for hint in RATE_LIMIT_HINTS):
            return True, False, "rate_limited"
        return True, False, "rate_limited"

    if response.status_code in (401, 403) and any(hint in message_blob for hint in QUOTA_HINTS):
        return False, True, "quota_exceeded"

    if retry_after and response.status_code >= 500:
        return True, False, "upstream_retry_after"

    return False, False, "ok"
