from __future__ import annotations

import os
from pathlib import Path

import pytest

from poolswitch.config import _apply_env_overrides, _load_yaml, AppConfig, KeyConfig, load_config


def test_load_yaml_missing(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yaml"
    with pytest.raises(FileNotFoundError):
        _load_yaml(missing)


def test_load_yaml_requires_mapping(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("- item", encoding="utf-8")
    with pytest.raises(ValueError):
        _load_yaml(config_path)


def test_apply_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POOLSWITCH_LISTEN_HOST", "0.0.0.0")
    monkeypatch.setenv("POOLSWITCH_LISTEN_PORT", "9090")
    monkeypatch.setenv("POOLSWITCH_UPSTREAM_BASE_URL", "https://example.com")
    monkeypatch.setenv("POOLSWITCH_KEYS", "sk-1, sk-2")
    monkeypatch.setenv("POOLSWITCH_STORAGE_BACKEND", "redis")
    monkeypatch.setenv("POOLSWITCH_REDIS_URL", "redis://example")
    monkeypatch.setenv("POOLSWITCH_SQLITE_PATH", "runtime.db")

    result = _apply_env_overrides({})

    assert result["listen_host"] == "0.0.0.0"
    assert result["listen_port"] == "9090"
    assert result["upstream_base_url"] == "https://example.com"
    assert result["keys"] == [{"value": "sk-1"}, {"value": "sk-2"}]
    assert result["storage"]["backend"] == "redis"
    assert result["storage"]["redis_url"] == "redis://example"
    assert result["storage"]["sqlite_path"] == "runtime.db"


def test_apply_env_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ.keys()):
        if name.startswith("POOLSWITCH_"):
            monkeypatch.delenv(name, raising=False)

    original = {"listen_host": "127.0.0.1"}
    result = _apply_env_overrides(original)

    assert result == original


def test_app_config_requires_keys() -> None:
    with pytest.raises(ValueError):
        AppConfig(upstream_base_url="https://example.com", keys=[])


def test_key_config_to_definition_metadata() -> None:
    key = KeyConfig(id=None, value="sk", monthly_quota=5, metadata={"region": "us"})
    definition = key.to_definition(index=2)
    assert definition.id == "key-2"
    assert definition.monthly_quota == 5
    assert definition.metadata == {"region": "us"}


def test_load_config_overrides(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
upstream_base_url: https://example.com
keys:
  - value: sk
listen_port: 8080
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path, overrides={"listen_port": 9090})
    assert config.listen_port == 9090


def test_apply_env_overrides_storage_without_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POOLSWITCH_STORAGE_BACKEND", "redis")
    result = _apply_env_overrides({})
    assert result["storage"]["backend"] == "redis"
    assert "redis_url" not in result["storage"]


def test_load_config_from_env_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POOLSWITCH_UPSTREAM_BASE_URL", "https://env.example.com")
    monkeypatch.setenv("POOLSWITCH_KEYS", "sk-env")

    config = load_config()

    assert config.upstream_base_url == "https://env.example.com"
    assert config.key_definitions[0].value == "sk-env"


