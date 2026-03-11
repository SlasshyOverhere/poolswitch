from __future__ import annotations

import pytest

from poolswitch.config import AppConfig, KeyConfig, StorageConfig
from poolswitch.core.factory import build_key_pool, build_state_store
from poolswitch.metrics import Metrics
from poolswitch.storage import InMemoryKeyStateStore, RedisKeyStateStore, SQLiteKeyStateStore


def test_build_state_store_memory() -> None:
    config = AppConfig(upstream_base_url="https://example.com", keys=[KeyConfig(value="sk")])
    store = build_state_store(config)
    assert isinstance(store, InMemoryKeyStateStore)


def test_build_state_store_sqlite(tmp_path) -> None:
    storage = StorageConfig(backend="sqlite", sqlite_path=str(tmp_path / "state.db"))
    config = AppConfig(upstream_base_url="https://example.com", keys=[KeyConfig(value="sk")], storage=storage)
    store = build_state_store(config)
    assert isinstance(store, SQLiteKeyStateStore)


def test_build_state_store_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("poolswitch.storage.redis_store.Redis.from_url", lambda *_args, **_kwargs: object())
    storage = StorageConfig(backend="redis", redis_url="redis://example")
    config = AppConfig(upstream_base_url="https://example.com", keys=[KeyConfig(value="sk")], storage=storage)
    store = build_state_store(config)
    assert isinstance(store, RedisKeyStateStore)


@pytest.mark.asyncio
async def test_build_key_pool() -> None:
    config = AppConfig(upstream_base_url="https://example.com", keys=[KeyConfig(value="sk")])
    pool = await build_key_pool(config, Metrics())
    records = await pool.list_records()
    assert len(records) == 1

