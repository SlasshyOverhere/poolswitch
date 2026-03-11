from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from poolswitch.models import APIKeyDefinition


StrategyName = Literal["round_robin", "least_used", "random", "quota_failover"]
StorageBackendName = Literal["memory", "redis", "sqlite"]


class StorageConfig(BaseModel):
    backend: StorageBackendName = "memory"
    redis_url: str = "redis://localhost:6379/0"
    sqlite_path: str = "poolswitch.db"
    namespace: str = "poolswitch"


class KeyConfig(BaseModel):
    id: str | None = None
    value: str
    monthly_quota: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_definition(self, index: int) -> APIKeyDefinition:
        return APIKeyDefinition(
            id=self.id or f"key-{index}",
            value=self.value,
            monthly_quota=self.monthly_quota,
            metadata=self.metadata,
        )


class AppConfig(BaseModel):
    listen_host: str = "127.0.0.1"
    listen_port: int = 8080
    upstream_base_url: str
    auth_header_name: str = "Authorization"
    auth_scheme: str | None = "Bearer"
    strategy: StrategyName = "quota_failover"
    retry_attempts: int = 3
    cooldown_seconds: int = 3600
    request_timeout_seconds: float = 60.0
    connect_timeout_seconds: float = 10.0
    rate_limit_per_second: float = 50.0
    metrics_enabled: bool = True
    retryable_methods: list[str] = Field(default_factory=lambda: ["GET", "HEAD", "OPTIONS", "DELETE", "POST"])
    keys: list[KeyConfig]
    storage: StorageConfig = Field(default_factory=StorageConfig)

    @field_validator("keys")
    @classmethod
    def validate_keys(cls, value: list[KeyConfig]) -> list[KeyConfig]:
        if not value:
            raise ValueError("At least one API key must be configured.")
        return value

    @property
    def key_definitions(self) -> list[APIKeyDefinition]:
        return [key.to_definition(index=index) for index, key in enumerate(self.keys, start=1)]


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise ValueError("Config file must contain a top-level mapping.")
    return loaded


def _apply_env_overrides(data: dict[str, Any]) -> dict[str, Any]:
    result = dict(data)
    mappings = {
        "POOLSWITCH_LISTEN_HOST": "listen_host",
        "POOLSWITCH_LISTEN_PORT": "listen_port",
        "POOLSWITCH_UPSTREAM_BASE_URL": "upstream_base_url",
        "POOLSWITCH_AUTH_HEADER_NAME": "auth_header_name",
        "POOLSWITCH_AUTH_SCHEME": "auth_scheme",
        "POOLSWITCH_STRATEGY": "strategy",
        "POOLSWITCH_RETRY_ATTEMPTS": "retry_attempts",
        "POOLSWITCH_COOLDOWN_SECONDS": "cooldown_seconds",
        "POOLSWITCH_RATE_LIMIT_PER_SECOND": "rate_limit_per_second",
    }
    for env_name, config_key in mappings.items():
        if env_name in os.environ:
            result[config_key] = os.environ[env_name]

    keys_env = os.getenv("POOLSWITCH_KEYS")
    if keys_env:
        result["keys"] = [{"value": value.strip()} for value in keys_env.split(",") if value.strip()]

    storage_backend = os.getenv("POOLSWITCH_STORAGE_BACKEND")
    if storage_backend:
        storage = dict(result.get("storage", {}))
        storage["backend"] = storage_backend
        if os.getenv("POOLSWITCH_REDIS_URL"):
            storage["redis_url"] = os.environ["POOLSWITCH_REDIS_URL"]
        if os.getenv("POOLSWITCH_SQLITE_PATH"):
            storage["sqlite_path"] = os.environ["POOLSWITCH_SQLITE_PATH"]
        result["storage"] = storage

    return result


def load_config(config_path: str | Path | None = None, overrides: dict[str, Any] | None = None) -> AppConfig:
    data: dict[str, Any] = {}
    if config_path:
        data.update(_load_yaml(Path(config_path)))
    data = _apply_env_overrides(data)
    if overrides:
        data.update({key: value for key, value in overrides.items() if value is not None})
    return AppConfig.model_validate(data)


