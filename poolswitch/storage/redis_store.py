from __future__ import annotations

import json
from datetime import datetime
from typing import Iterable

from redis.asyncio import Redis

from poolswitch.models import APIKeyDefinition, APIKeyState
from poolswitch.storage.base import KeyStateStore


def _serialize_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _deserialize_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class RedisKeyStateStore(KeyStateStore):
    def __init__(self, redis_url: str, namespace: str = "poolswitch") -> None:
        self.redis = Redis.from_url(redis_url, decode_responses=True)
        self.namespace = namespace

    def _key(self, key_id: str) -> str:
        return f"{self.namespace}:key:{key_id}"

    async def initialize(self, definitions: Iterable[APIKeyDefinition]) -> None:
        for definition in definitions:
            redis_key = self._key(definition.id)
            if await self.redis.exists(redis_key):
                continue
            await self.redis.set(redis_key, json.dumps(self._to_payload(APIKeyState(key_id=definition.id))))

    async def get_states(self) -> dict[str, APIKeyState]:
        states: dict[str, APIKeyState] = {}
        async for redis_key in self.redis.scan_iter(match=f"{self.namespace}:key:*"):
            payload = await self.redis.get(redis_key)
            if payload:
                state = self._from_payload(json.loads(payload))
                states[state.key_id] = state
        return states

    async def get_state(self, key_id: str) -> APIKeyState:
        payload = await self.redis.get(self._key(key_id))
        if payload is None:
            raise KeyError(key_id)
        return self._from_payload(json.loads(payload))

    async def upsert_state(self, state: APIKeyState) -> None:
        await self.redis.set(self._key(state.key_id), json.dumps(self._to_payload(state)))

    async def delete_state(self, key_id: str) -> None:
        await self.redis.delete(self._key(key_id))

    @staticmethod
    def _to_payload(state: APIKeyState) -> dict[str, str | int | None]:
        return {
            "key_id": state.key_id,
            "total_requests": state.total_requests,
            "error_count": state.error_count,
            "failover_count": state.failover_count,
            "estimated_remaining_quota": state.estimated_remaining_quota,
            "last_used_at": _serialize_datetime(state.last_used_at),
            "cooldown_until": _serialize_datetime(state.cooldown_until),
            "consecutive_rate_limits": state.consecutive_rate_limits,
        }

    @staticmethod
    def _from_payload(payload: dict[str, str | int | None]) -> APIKeyState:
        return APIKeyState(
            key_id=str(payload["key_id"]),
            total_requests=int(payload["total_requests"]),
            error_count=int(payload["error_count"]),
            failover_count=int(payload["failover_count"]),
            estimated_remaining_quota=(
                int(payload["estimated_remaining_quota"]) if payload["estimated_remaining_quota"] is not None else None
            ),
            last_used_at=_deserialize_datetime(payload["last_used_at"]),
            cooldown_until=_deserialize_datetime(payload["cooldown_until"]),
            consecutive_rate_limits=int(payload["consecutive_rate_limits"]),
        )

