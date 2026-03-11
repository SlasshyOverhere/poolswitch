from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from poolswitch.models import APIKeyDefinition, APIKeyState


class KeyStateStore(ABC):
    @abstractmethod
    async def initialize(self, definitions: Iterable[APIKeyDefinition]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_states(self) -> dict[str, APIKeyState]:
        raise NotImplementedError

    @abstractmethod
    async def get_state(self, key_id: str) -> APIKeyState:
        raise NotImplementedError

    @abstractmethod
    async def upsert_state(self, state: APIKeyState) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete_state(self, key_id: str) -> None:
        raise NotImplementedError

