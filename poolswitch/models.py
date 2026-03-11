from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class APIKeyDefinition:
    id: str
    value: str
    monthly_quota: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class APIKeyState:
    key_id: str
    total_requests: int = 0
    error_count: int = 0
    failover_count: int = 0
    estimated_remaining_quota: int | None = None
    last_used_at: datetime | None = None
    cooldown_until: datetime | None = None
    consecutive_rate_limits: int = 0

    @property
    def is_in_cooldown(self) -> bool:
        return self.cooldown_until is not None and self.cooldown_until > utc_now()


@dataclass(slots=True)
class KeyRecord:
    definition: APIKeyDefinition
    state: APIKeyState
