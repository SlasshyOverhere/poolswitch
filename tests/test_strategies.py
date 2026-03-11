from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from poolswitch.models import APIKeyDefinition, APIKeyState, KeyRecord
from poolswitch.strategies import (
    LeastUsedStrategy,
    QuotaFailoverStrategy,
    RandomStrategy,
    RoundRobinStrategy,
    build_strategy,
)
from poolswitch.strategies.impl import _timestamp_or_minimum


def _record(key_id: str, **state_kwargs) -> KeyRecord:
    return KeyRecord(
        definition=APIKeyDefinition(id=key_id, value=f"sk-{key_id}"),
        state=APIKeyState(key_id=key_id, **state_kwargs),
    )


@pytest.mark.asyncio
async def test_round_robin_cycles() -> None:
    strategy = RoundRobinStrategy()
    records = [_record("a"), _record("b")]

    first = await strategy.choose(records)
    second = await strategy.choose(records)
    third = await strategy.choose(records)

    assert [first.definition.id, second.definition.id, third.definition.id] == ["a", "b", "a"]


@pytest.mark.asyncio
async def test_least_used_prefers_low_counts() -> None:
    strategy = LeastUsedStrategy()
    base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    records = [
        _record("a", total_requests=5, error_count=1, last_used_at=base_time),
        _record("b", total_requests=2, error_count=2, last_used_at=base_time + timedelta(seconds=5)),
        _record("c", total_requests=2, error_count=1, last_used_at=base_time + timedelta(seconds=1)),
    ]

    selected = await strategy.choose(records)

    assert selected.definition.id == "c"


@pytest.mark.asyncio
async def test_random_strategy_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    strategy = RandomStrategy()
    records = [_record("a"), _record("b"), _record("c")]

    monkeypatch.setattr("poolswitch.strategies.impl.random.choice", lambda items: items[-1])
    selected = await strategy.choose(records)

    assert selected.definition.id == "c"


@pytest.mark.asyncio
async def test_quota_failover_prefers_healthy_high_quota() -> None:
    strategy = QuotaFailoverStrategy()
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    records = [
        _record(
            "a",
            estimated_remaining_quota=5,
            cooldown_until=now + timedelta(seconds=10),
            consecutive_rate_limits=1,
        ),
        _record(
            "b",
            estimated_remaining_quota=2,
            cooldown_until=None,
            consecutive_rate_limits=0,
        ),
        _record(
            "c",
            estimated_remaining_quota=10,
            cooldown_until=None,
            consecutive_rate_limits=0,
        ),
    ]

    selected = await strategy.choose(records)

    assert selected.definition.id == "c"


def test_build_strategy() -> None:
    assert isinstance(build_strategy("round_robin"), RoundRobinStrategy)
    assert isinstance(build_strategy("least_used"), LeastUsedStrategy)
    assert isinstance(build_strategy("random"), RandomStrategy)
    assert isinstance(build_strategy("quota_failover"), QuotaFailoverStrategy)


def test_timestamp_or_minimum() -> None:
    assert _timestamp_or_minimum(None) == 0.0
    moment = datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert _timestamp_or_minimum(moment) == moment.timestamp()

