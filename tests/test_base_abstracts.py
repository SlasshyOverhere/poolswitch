from __future__ import annotations

import pytest

from poolswitch.models import APIKeyDefinition, APIKeyState, KeyRecord
from poolswitch.storage.base import KeyStateStore
from poolswitch.strategies.base import RoutingStrategy


class DummyStore(KeyStateStore):
    async def initialize(self, definitions):
        return await super().initialize(definitions)

    async def get_states(self) -> dict[str, APIKeyState]:
        return await super().get_states()

    async def get_state(self, key_id: str) -> APIKeyState:
        return await super().get_state(key_id)

    async def upsert_state(self, state: APIKeyState) -> None:
        return await super().upsert_state(state)

    async def delete_state(self, key_id: str) -> None:
        return await super().delete_state(key_id)


class DummyStrategy(RoutingStrategy):
    async def choose(self, candidates: list[KeyRecord]) -> KeyRecord:
        return await super().choose(candidates)


@pytest.mark.asyncio
async def test_key_state_store_abstracts() -> None:
    store = DummyStore()
    with pytest.raises(NotImplementedError):
        await store.initialize([APIKeyDefinition(id="a", value="sk")])
    with pytest.raises(NotImplementedError):
        await store.get_states()
    with pytest.raises(NotImplementedError):
        await store.get_state("a")
    with pytest.raises(NotImplementedError):
        await store.upsert_state(APIKeyState(key_id="a"))
    with pytest.raises(NotImplementedError):
        await store.delete_state("a")


@pytest.mark.asyncio
async def test_routing_strategy_abstract() -> None:
    strategy = DummyStrategy()
    record = KeyRecord(definition=APIKeyDefinition(id="a", value="sk"), state=APIKeyState(key_id="a"))
    with pytest.raises(NotImplementedError):
        await strategy.choose([record])

