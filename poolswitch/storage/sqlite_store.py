from __future__ import annotations

from datetime import datetime
from typing import Iterable

import aiosqlite

from poolswitch.models import APIKeyDefinition, APIKeyState
from poolswitch.storage.base import KeyStateStore


def _as_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _from_iso(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class SQLiteKeyStateStore(KeyStateStore):
    def __init__(self, path: str) -> None:
        self.path = path

    async def initialize(self, definitions: Iterable[APIKeyDefinition]) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS key_state (
                    key_id TEXT PRIMARY KEY,
                    total_requests INTEGER NOT NULL,
                    error_count INTEGER NOT NULL,
                    failover_count INTEGER NOT NULL,
                    estimated_remaining_quota INTEGER NULL,
                    last_used_at TEXT NULL,
                    cooldown_until TEXT NULL,
                    consecutive_rate_limits INTEGER NOT NULL
                )
                """
            )
            for definition in definitions:
                await db.execute(
                    """
                    INSERT INTO key_state (
                        key_id,
                        total_requests,
                        error_count,
                        failover_count,
                        estimated_remaining_quota,
                        last_used_at,
                        cooldown_until,
                        consecutive_rate_limits
                    ) VALUES (?, 0, 0, 0, NULL, NULL, NULL, 0)
                    ON CONFLICT(key_id) DO NOTHING
                    """,
                    (definition.id,),
                )
            await db.commit()

    async def get_states(self) -> dict[str, APIKeyState]:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute("SELECT * FROM key_state") as cursor:
                rows = await cursor.fetchall()
        return {row[0]: self._row_to_state(row) for row in rows}

    async def get_state(self, key_id: str) -> APIKeyState:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute("SELECT * FROM key_state WHERE key_id = ?", (key_id,)) as cursor:
                row = await cursor.fetchone()
        if row is None:
            raise KeyError(key_id)
        return self._row_to_state(row)

    async def upsert_state(self, state: APIKeyState) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO key_state (
                    key_id,
                    total_requests,
                    error_count,
                    failover_count,
                    estimated_remaining_quota,
                    last_used_at,
                    cooldown_until,
                    consecutive_rate_limits
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(key_id) DO UPDATE SET
                    total_requests = excluded.total_requests,
                    error_count = excluded.error_count,
                    failover_count = excluded.failover_count,
                    estimated_remaining_quota = excluded.estimated_remaining_quota,
                    last_used_at = excluded.last_used_at,
                    cooldown_until = excluded.cooldown_until,
                    consecutive_rate_limits = excluded.consecutive_rate_limits
                """,
                (
                    state.key_id,
                    state.total_requests,
                    state.error_count,
                    state.failover_count,
                    state.estimated_remaining_quota,
                    _as_iso(state.last_used_at),
                    _as_iso(state.cooldown_until),
                    state.consecutive_rate_limits,
                ),
            )
            await db.commit()

    async def delete_state(self, key_id: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM key_state WHERE key_id = ?", (key_id,))
            await db.commit()

    @staticmethod
    def _row_to_state(row: tuple) -> APIKeyState:
        return APIKeyState(
            key_id=row[0],
            total_requests=row[1],
            error_count=row[2],
            failover_count=row[3],
            estimated_remaining_quota=row[4],
            last_used_at=_from_iso(row[5]),
            cooldown_until=_from_iso(row[6]),
            consecutive_rate_limits=row[7],
        )

