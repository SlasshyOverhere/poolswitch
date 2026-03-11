from __future__ import annotations

import asyncio

import pytest

from poolswitch.retry import RetryDecision, RetryPolicy


def test_retry_policy_no_retry_when_not_retryable() -> None:
    policy = RetryPolicy(attempts=3)
    decision = policy.for_attempt(attempt_number=1, retryable=False, reason="nope")
    assert decision == RetryDecision(should_retry=False, delay_seconds=0.0, reason="nope")


def test_retry_policy_no_retry_after_attempts() -> None:
    policy = RetryPolicy(attempts=2)
    decision = policy.for_attempt(attempt_number=2, retryable=True, reason="done")
    assert decision.should_retry is False


def test_retry_policy_backoff_and_jitter(monkeypatch: pytest.MonkeyPatch) -> None:
    policy = RetryPolicy(attempts=3, base_backoff_seconds=1.0, max_backoff_seconds=10.0, jitter_ratio=0.5)
    monkeypatch.setattr("poolswitch.retry.policy.random.random", lambda: 0.0)

    decision = policy.for_attempt(attempt_number=1, retryable=True, reason="rate_limited")
    assert decision.should_retry is True
    assert decision.delay_seconds == 1.0


@pytest.mark.asyncio
async def test_retry_sleep_only_when_needed(monkeypatch: pytest.MonkeyPatch) -> None:
    policy = RetryPolicy(attempts=1)
    slept: list[float] = []

    async def fake_sleep(delay: float) -> None:
        slept.append(delay)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    await policy.sleep(RetryDecision(should_retry=True, delay_seconds=0.0, reason=""))
    await policy.sleep(RetryDecision(should_retry=True, delay_seconds=1.5, reason=""))

    assert slept == [1.5]

