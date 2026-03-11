from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from poolswitch.models import APIKeyDefinition, APIKeyState
from poolswitch.storage.base import KeyStateStore


class InMemoryKeyStateStore(KeyStateStore):
    def __init__(self) -> None:
        self._states: dict[str, APIKeyState] = {}

    async def initialize(self, definitions: Iterable[APIKeyDefinition]) -> None:
        for definition in definitions:
            self._states.setdefault(definition.id, APIKeyState(key_id=definition.id))

    async def get_states(self) -> dict[str, APIKeyState]:
        return {key_id: replace(state) for key_id, state in self._states.items()}

    async def get_state(self, key_id: str) -> APIKeyState:
        return replace(self._states[key_id])

    async def upsert_state(self, state: APIKeyState) -> None:
        self._states[state.key_id] = replace(state)

    async def delete_state(self, key_id: str) -> None:
        self._states.pop(key_id, None)

