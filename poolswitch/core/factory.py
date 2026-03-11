from __future__ import annotations

from poolswitch.config import AppConfig
from poolswitch.core.key_pool import KeyPool
from poolswitch.metrics import Metrics
from poolswitch.storage import InMemoryKeyStateStore, RedisKeyStateStore, SQLiteKeyStateStore
from poolswitch.storage.base import KeyStateStore
from poolswitch.strategies import build_strategy


def build_state_store(config: AppConfig) -> KeyStateStore:
    if config.storage.backend == "memory":
        return InMemoryKeyStateStore()
    if config.storage.backend == "redis":
        return RedisKeyStateStore(redis_url=config.storage.redis_url, namespace=config.storage.namespace)
    return SQLiteKeyStateStore(path=config.storage.sqlite_path)


async def build_key_pool(config: AppConfig, metrics: Metrics) -> KeyPool:
    state_store = build_state_store(config)
    strategy = build_strategy(config.strategy)
    pool = KeyPool(
        config=config,
        definitions=config.key_definitions,
        state_store=state_store,
        strategy=strategy,
        metrics=metrics,
    )
    await pool.initialize()
    return pool


