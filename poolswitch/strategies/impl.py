from __future__ import annotations

import asyncio
import random
from collections.abc import Callable
from datetime import datetime

from poolswitch.config import StrategyName
from poolswitch.models import KeyRecord
from poolswitch.strategies.base import RoutingStrategy


def _timestamp_or_minimum(value: datetime | None) -> float:
    return value.timestamp() if value else 0.0


class RoundRobinStrategy(RoutingStrategy):
    def __init__(self) -> None:
        self._index = 0
        self._lock = asyncio.Lock()

    async def choose(self, candidates: list[KeyRecord]) -> KeyRecord:
        async with self._lock:
            selected = candidates[self._index % len(candidates)]
            self._index += 1
            return selected


class LeastUsedStrategy(RoutingStrategy):
    async def choose(self, candidates: list[KeyRecord]) -> KeyRecord:
        return min(
            candidates,
            key=lambda candidate: (
                candidate.state.total_requests,
                candidate.state.error_count,
                _timestamp_or_minimum(candidate.state.last_used_at),
            ),
        )


class RandomStrategy(RoutingStrategy):
    async def choose(self, candidates: list[KeyRecord]) -> KeyRecord:
        return random.choice(candidates)


class QuotaFailoverStrategy(RoutingStrategy):
    async def choose(self, candidates: list[KeyRecord]) -> KeyRecord:
        return min(
            candidates,
            key=lambda candidate: (
                0 if not candidate.state.is_in_cooldown else 1,
                candidate.state.estimated_remaining_quota is None,
                -(candidate.state.estimated_remaining_quota or 0),
                candidate.state.consecutive_rate_limits,
                candidate.state.error_count,
                candidate.state.total_requests,
                _timestamp_or_minimum(candidate.state.last_used_at),
            ),
        )


def build_strategy(name: StrategyName) -> RoutingStrategy:
    strategies: dict[StrategyName, Callable[[], RoutingStrategy]] = {
        "round_robin": RoundRobinStrategy,
        "least_used": LeastUsedStrategy,
        "random": RandomStrategy,
        "quota_failover": QuotaFailoverStrategy,
    }
    return strategies[name]()

