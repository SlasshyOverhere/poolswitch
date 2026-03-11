from __future__ import annotations

import pytest

from poolswitch.config import AppConfig, KeyConfig
from poolswitch.core.factory import build_key_pool
from poolswitch.errors import NoHealthyKeysError
from poolswitch.metrics import Metrics
from poolswitch.models import APIKeyDefinition, APIKeyState
from poolswitch.storage.base import KeyStateStore


@pytest.mark.asyncio
async def test_acquire_key_no_healthy() -> None:
    config = AppConfig(
        upstream_base_url="https://example.com",
        cooldown_seconds=60,
        keys=[KeyConfig(id="primary", value="sk-primary")],
    )
    pool = await build_key_pool(config, Metrics())
    await pool.mark_key_quota_exhausted("primary", "quota_exceeded")

    with pytest.raises(NoHealthyKeysError):
        await pool.acquire_key()


@pytest.mark.asyncio
async def test_record_transient_error_and_failover() -> None:
    config = AppConfig(
        upstream_base_url="https://example.com",
        keys=[KeyConfig(id="primary", value="sk-primary")],
    )
    pool = await build_key_pool(config, Metrics())

    await pool.record_transient_error("primary", "rate_limited")
    await pool.record_failover("primary")

    records = await pool.list_records(include_cooldown=True)
    state = records[0].state

    assert state.error_count == 1
    assert state.consecutive_rate_limits == 1
    assert state.failover_count == 1


@pytest.mark.asyncio
async def test_add_and_remove_key() -> None:
    config = AppConfig(upstream_base_url="https://example.com", keys=[KeyConfig(id="primary", value="sk-primary")])
    pool = await build_key_pool(config, Metrics())

    await pool.add_key(APIKeyDefinition(id="secondary", value="sk-secondary"))
    records = await pool.list_records()
    assert {record.definition.id for record in records} == {"primary", "secondary"}

    await pool.remove_key("primary")
    records = await pool.list_records()
    assert {record.definition.id for record in records} == {"secondary"}


class EmptyStateStore(KeyStateStore):
    def __init__(self) -> None:
        self.upserted: list[str] = []

    async def initialize(self, definitions) -> None:
        return None

    async def get_states(self) -> dict[str, APIKeyState]:
        return {}

    async def get_state(self, key_id: str) -> APIKeyState:
        return APIKeyState(key_id=key_id)

    async def upsert_state(self, state: APIKeyState) -> None:
        self.upserted.append(state.key_id)

    async def delete_state(self, key_id: str) -> None:
        return None


@pytest.mark.asyncio
async def test_initialize_adds_missing_state() -> None:
    config = AppConfig(upstream_base_url="https://example.com", keys=[KeyConfig(id="primary", value="sk-primary")])
    store = EmptyStateStore()

    pool = await build_key_pool(config, Metrics())
    pool.state_store = store
    await pool.initialize()

    assert store.upserted == ["primary"]


@pytest.mark.asyncio
async def test_mark_quota_exhausted_preserves_zero() -> None:
    config = AppConfig(upstream_base_url="https://example.com", cooldown_seconds=60, keys=[KeyConfig(id="primary", value="sk-primary")])
    pool = await build_key_pool(config, Metrics())

    state = await pool.state_store.get_state("primary")
    state.estimated_remaining_quota = 0
    await pool.state_store.upsert_state(state)

    await pool.mark_key_quota_exhausted("primary", "quota_exceeded")

    updated = await pool.state_store.get_state("primary")
    assert updated.estimated_remaining_quota == 0

