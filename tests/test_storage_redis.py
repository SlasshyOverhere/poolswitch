from __future__ import annotations

import fnmatch
from datetime import datetime, timezone

import pytest

from poolswitch.models import APIKeyDefinition, APIKeyState
from poolswitch.storage.redis_store import (
    RedisKeyStateStore,
    _deserialize_datetime,
    _serialize_datetime,
)


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str | None] = {}

    async def exists(self, key: str) -> int:
        return 1 if key in self.store else 0

    async def set(self, key: str, value: str) -> None:
        self.store[key] = value

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)

    async def scan_iter(self, match: str):
        for key in list(self.store.keys()):
            if fnmatch.fnmatch(key, match):
                yield key


def test_serialize_helpers() -> None:
    assert _serialize_datetime(None) is None
    assert _deserialize_datetime(None) is None
    moment = datetime(2024, 1, 1, tzinfo=timezone.utc)
    payload = _serialize_datetime(moment)
    assert payload == moment.isoformat()
    assert _deserialize_datetime(payload) == moment


@pytest.mark.asyncio
async def test_redis_store_crud(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRedis()
    monkeypatch.setattr("poolswitch.storage.redis_store.Redis.from_url", lambda *_args, **_kwargs: fake)

    store = RedisKeyStateStore(redis_url="redis://example")
    await store.initialize([APIKeyDefinition(id="a", value="sk-a")])

    state = await store.get_state("a")
    assert state.key_id == "a"

    state.total_requests = 5
    await store.upsert_state(state)

    updated = await store.get_state("a")
    assert updated.total_requests == 5

    await store.delete_state("a")
    with pytest.raises(KeyError):
        await store.get_state("a")


@pytest.mark.asyncio
async def test_redis_store_initialize_skips_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRedis()
    monkeypatch.setattr("poolswitch.storage.redis_store.Redis.from_url", lambda *_args, **_kwargs: fake)

    store = RedisKeyStateStore(redis_url="redis://example", namespace="pool")
    pre_state = APIKeyState(key_id="existing", total_requests=2)
    await store.upsert_state(pre_state)

    await store.initialize([APIKeyDefinition(id="existing", value="sk-existing"), APIKeyDefinition(id="new", value="sk-new")])

    states = await store.get_states()
    assert set(states.keys()) == {"existing", "new"}
    assert states["existing"].total_requests == 2


@pytest.mark.asyncio
async def test_redis_store_skips_empty_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRedis()
    monkeypatch.setattr("poolswitch.storage.redis_store.Redis.from_url", lambda *_args, **_kwargs: fake)

    store = RedisKeyStateStore(redis_url="redis://example", namespace="pool")
    fake.store["pool:key:empty"] = None

    states = await store.get_states()
    assert states == {}

