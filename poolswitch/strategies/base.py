from __future__ import annotations

from abc import ABC, abstractmethod

from poolswitch.models import KeyRecord


class RoutingStrategy(ABC):
    @abstractmethod
    async def choose(self, candidates: list[KeyRecord]) -> KeyRecord:
        raise NotImplementedError

