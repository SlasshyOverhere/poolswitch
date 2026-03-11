from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import timedelta

from poolswitch.config import AppConfig
from poolswitch.errors import NoHealthyKeysError
from poolswitch.metrics import Metrics
from poolswitch.models import APIKeyDefinition, APIKeyState, KeyRecord, utc_now
from poolswitch.storage.base import KeyStateStore
from poolswitch.strategies.base import RoutingStrategy


class KeyPool:
    def __init__(
        self,
        config: AppConfig,
        definitions: Iterable[APIKeyDefinition],
        state_store: KeyStateStore,
        strategy: RoutingStrategy,
        metrics: Metrics,
    ) -> None:
        self.config = config
        self.definitions = {definition.id: definition for definition in definitions}
        self.state_store = state_store
        self.strategy = strategy
        self.metrics = metrics
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        await self.state_store.initialize(self.definitions.values())
        states = await self.state_store.get_states()
        for key_id in self.definitions:
            if key_id not in states:
                await self.state_store.upsert_state(APIKeyState(key_id=key_id))

    async def list_records(self, include_cooldown: bool = True) -> list[KeyRecord]:
        states = await self.state_store.get_states()
        records = []
        for key_id, definition in self.definitions.items():
            state = states.get(key_id, APIKeyState(key_id=key_id))
            if include_cooldown or not state.is_in_cooldown:
                records.append(KeyRecord(definition=definition, state=state))
        return records

    async def acquire_key(self, excluded_key_ids: set[str] | None = None) -> KeyRecord:
        excluded = excluded_key_ids or set()
        async with self._lock:
            records = await self.list_records(include_cooldown=False)
            candidates = [record for record in records if record.definition.id not in excluded]
            if not candidates:
                records = await self.list_records(include_cooldown=True)
                candidates = [record for record in records if record.definition.id not in excluded and not record.state.is_in_cooldown]
            if not candidates:
                raise NoHealthyKeysError("All API keys are in cooldown or unavailable.")
            return await self.strategy.choose(candidates)

    async def record_success(self, key_id: str, remaining_quota: int | None = None) -> None:
        state = await self.state_store.get_state(key_id)
        state.total_requests += 1
        state.last_used_at = utc_now()
        state.consecutive_rate_limits = 0
        state.cooldown_until = None
        if remaining_quota is not None:
            state.estimated_remaining_quota = remaining_quota
        await self.state_store.upsert_state(state)
        self.metrics.key_usage_total.labels(key_id=key_id).inc()
        self.metrics.key_cooldown.labels(key_id=key_id).set(0)

    async def record_transient_error(self, key_id: str, reason: str) -> None:
        state = await self.state_store.get_state(key_id)
        state.error_count += 1
        state.last_used_at = utc_now()
        if reason == "rate_limited":
            state.consecutive_rate_limits += 1
        await self.state_store.upsert_state(state)
        self.metrics.key_errors_total.labels(key_id=key_id, reason=reason).inc()

    async def mark_key_quota_exhausted(self, key_id: str, reason: str) -> None:
        state = await self.state_store.get_state(key_id)
        state.error_count += 1
        state.consecutive_rate_limits += 1
        state.cooldown_until = utc_now() + timedelta(seconds=self.config.cooldown_seconds)
        state.last_used_at = utc_now()
        if state.estimated_remaining_quota is None or state.estimated_remaining_quota > 0:
            state.estimated_remaining_quota = 0
        await self.state_store.upsert_state(state)
        self.metrics.key_errors_total.labels(key_id=key_id, reason=reason).inc()
        self.metrics.key_cooldown.labels(key_id=key_id).set(1)

    async def record_failover(self, key_id: str) -> None:
        state = await self.state_store.get_state(key_id)
        state.failover_count += 1
        await self.state_store.upsert_state(state)

    async def add_key(self, definition: APIKeyDefinition) -> None:
        self.definitions[definition.id] = definition
        await self.state_store.upsert_state(APIKeyState(key_id=definition.id))

    async def remove_key(self, key_id: str) -> None:
        self.definitions.pop(key_id, None)
        await self.state_store.delete_state(key_id)


