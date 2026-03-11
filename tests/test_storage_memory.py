from __future__ import annotations

import pytest

from poolswitch.models import APIKeyDefinition, APIKeyState
from poolswitch.storage.memory import InMemoryKeyStateStore


@pytest.mark.asyncio
async def test_memory_store_crud() -> None:
    store = InMemoryKeyStateStore()
    definitions = [APIKeyDefinition(id="primary", value="sk-primary")]

    await store.initialize(definitions)
    states = await store.get_states()
    assert "primary" in states

    state = await store.get_state("primary")
    state.total_requests = 3
    await store.upsert_state(state)

    fetched = await store.get_state("primary")
    assert fetched.total_requests == 3

    await store.delete_state("primary")
    with pytest.raises(KeyError):
        await store.get_state("primary")


@pytest.mark.asyncio
async def test_get_states_returns_copies() -> None:
    store = InMemoryKeyStateStore()
    await store.initialize([APIKeyDefinition(id="a", value="sk-a")])

    states = await store.get_states()
    states["a"].total_requests = 10

    again = await store.get_state("a")
    assert again.total_requests == 0

