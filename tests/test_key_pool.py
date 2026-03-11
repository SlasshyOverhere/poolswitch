import pytest

from poolswitch.config import AppConfig, KeyConfig
from poolswitch.core.factory import build_key_pool
from poolswitch.metrics import Metrics


@pytest.mark.asyncio
async def test_quota_failover_prefers_highest_remaining_quota() -> None:
    config = AppConfig(
        upstream_base_url="https://example.com",
        strategy="quota_failover",
        keys=[
            KeyConfig(id="primary", value="sk-primary"),
            KeyConfig(id="secondary", value="sk-secondary"),
        ],
    )
    pool = await build_key_pool(config, Metrics())

    await pool.record_success("primary", remaining_quota=5)
    await pool.record_success("secondary", remaining_quota=25)

    selected = await pool.acquire_key()

    assert selected.definition.id == "secondary"


@pytest.mark.asyncio
async def test_quota_exhausted_key_enters_cooldown() -> None:
    config = AppConfig(
        upstream_base_url="https://example.com",
        cooldown_seconds=120,
        strategy="quota_failover",
        keys=[
            KeyConfig(id="primary", value="sk-primary"),
            KeyConfig(id="secondary", value="sk-secondary"),
        ],
    )
    pool = await build_key_pool(config, Metrics())

    await pool.mark_key_quota_exhausted("primary", "quota_exceeded")
    selected = await pool.acquire_key()
    records = await pool.list_records(include_cooldown=True)
    primary = next(record for record in records if record.definition.id == "primary")

    assert selected.definition.id == "secondary"
    assert primary.state.cooldown_until is not None
    assert primary.state.estimated_remaining_quota == 0

