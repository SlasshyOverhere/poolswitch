from __future__ import annotations

from datetime import datetime, timezone

import pytest

from poolswitch.models import APIKeyDefinition, APIKeyState
from poolswitch.storage.sqlite_store import SQLiteKeyStateStore, _as_iso, _from_iso


@pytest.mark.asyncio
async def test_sqlite_store_crud(tmp_path) -> None:
    db_path = tmp_path / "state.db"
    store = SQLiteKeyStateStore(str(db_path))
    await store.initialize([APIKeyDefinition(id="primary", value="sk-primary")])

    state = await store.get_state("primary")
    assert state.key_id == "primary"

    state.total_requests = 2
    await store.upsert_state(state)

    updated = await store.get_state("primary")
    assert updated.total_requests == 2

    await store.delete_state("primary")
    with pytest.raises(KeyError):
        await store.get_state("primary")


@pytest.mark.asyncio
async def test_sqlite_store_get_states(tmp_path) -> None:
    db_path = tmp_path / "state.db"
    store = SQLiteKeyStateStore(str(db_path))
    await store.initialize([APIKeyDefinition(id="a", value="sk-a"), APIKeyDefinition(id="b", value="sk-b")])

    states = await store.get_states()
    assert set(states.keys()) == {"a", "b"}


def test_iso_helpers() -> None:
    moment = datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert _from_iso(_as_iso(moment)) == moment
    assert _as_iso(None) is None
    assert _from_iso(None) is None


@pytest.mark.asyncio
async def test_sqlite_row_to_state(tmp_path) -> None:
    db_path = tmp_path / "state.db"
    store = SQLiteKeyStateStore(str(db_path))
    row = (
        "key",
        1,
        2,
        3,
        4,
        "2024-01-01T00:00:00+00:00",
        "2024-01-02T00:00:00+00:00",
        5,
    )
    state = store._row_to_state(row)
    assert isinstance(state, APIKeyState)
    assert state.failover_count == 3
    assert state.consecutive_rate_limits == 5

