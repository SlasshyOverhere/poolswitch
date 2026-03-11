from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass


@dataclass(slots=True)
class RetryDecision:
    should_retry: bool
    delay_seconds: float = 0.0
    reason: str = ""


class RetryPolicy:
    def __init__(
        self,
        attempts: int,
        base_backoff_seconds: float = 0.25,
        max_backoff_seconds: float = 5.0,
        jitter_ratio: float = 0.2,
    ) -> None:
        self.attempts = attempts
        self.base_backoff_seconds = base_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.jitter_ratio = jitter_ratio

    def for_attempt(self, attempt_number: int, retryable: bool, reason: str) -> RetryDecision:
        if not retryable or attempt_number >= self.attempts:
            return RetryDecision(should_retry=False, reason=reason)
        delay = min(self.base_backoff_seconds * (2 ** (attempt_number - 1)), self.max_backoff_seconds)
        jitter = delay * self.jitter_ratio * random.random()
        return RetryDecision(should_retry=True, delay_seconds=delay + jitter, reason=reason)

    async def sleep(self, decision: RetryDecision) -> None:
        if decision.delay_seconds > 0:
            await asyncio.sleep(decision.delay_seconds)
