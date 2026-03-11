from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import click
import uvicorn
import yaml

from poolswitch.config import AppConfig, load_config
from poolswitch.core.factory import build_key_pool
from poolswitch.metrics import Metrics
from poolswitch.proxy.app import create_app


def _configure_event_loop_policy() -> None:
    if not sys.platform.startswith("win"):
        return
    selector_policy = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if selector_policy is None:
        return
    asyncio.set_event_loop_policy(selector_policy())


def _load(config_path: str | None, listen_host: str | None, listen_port: int | None) -> AppConfig:
    overrides = {
        "listen_host": listen_host,
        "listen_port": listen_port,
    }
    return load_config(config_path=config_path, overrides=overrides)


def _read_config_file(path: str) -> dict[str, Any]:
    config_file = Path(path)
    with config_file.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise click.ClickException("Config file must contain a mapping.")
    return data


def _write_config_file(path: str, data: dict[str, Any]) -> None:
    config_file = Path(path)
    with config_file.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False)


@click.group()
def main() -> None:
    """PoolSwitch CLI."""


@main.command()
@click.option("--config", "config_path", type=click.Path(exists=True, dir_okay=False), required=False)
@click.option("--listen-host", type=str, required=False)
@click.option("--listen-port", type=int, required=False)
def start(config_path: str | None, listen_host: str | None, listen_port: int | None) -> None:
    """Start the local proxy server."""
    _configure_event_loop_policy()
    config = _load(config_path, listen_host, listen_port)
    app = create_app(config)
    uvicorn.run(
        app,
        host=config.listen_host,
        port=config.listen_port,
        log_level="info",
        timeout_graceful_shutdown=2,
    )


async def _status_json(config: AppConfig) -> str:
    metrics = Metrics()
    pool = await build_key_pool(config, metrics)
    records = await pool.list_records(include_cooldown=True)
    return json.dumps(
        {
            "listen": f"{config.listen_host}:{config.listen_port}",
            "strategy": config.strategy,
            "storage": config.storage.backend,
            "keys": [
                {
                    "id": record.definition.id,
                    "total_requests": record.state.total_requests,
                    "errors": record.state.error_count,
                    "failovers": record.state.failover_count,
                    "cooldown_until": record.state.cooldown_until.isoformat() if record.state.cooldown_until else None,
                }
                for record in records
            ],
        },
        indent=2,
    )


@main.command()
@click.option("--config", "config_path", type=click.Path(exists=True, dir_okay=False), required=False)
@click.option("--listen-host", type=str, required=False)
@click.option("--listen-port", type=int, required=False)
def status(config_path: str | None, listen_host: str | None, listen_port: int | None) -> None:
    """Print current key state."""
    config = _load(config_path, listen_host, listen_port)
    click.echo(asyncio.run(_status_json(config)))


@main.command("add-key")
@click.option("--config", "config_path", type=click.Path(exists=True, dir_okay=False), required=True)
@click.option("--key", "key_value", type=str, required=True)
@click.option("--key-id", type=str, required=True)
@click.option("--monthly-quota", type=int, required=False)
def add_key(config_path: str, key_value: str, key_id: str, monthly_quota: int | None) -> None:
    """Persist a new key into the YAML config."""
    data = _read_config_file(config_path)
    keys = list(data.get("keys", []))
    if any(isinstance(item, dict) and item.get("id") == key_id for item in keys):
        raise click.ClickException(f"Key id already exists: {key_id}")
    entry: dict[str, Any] = {"id": key_id, "value": key_value}
    if monthly_quota is not None:
        entry["monthly_quota"] = monthly_quota
    keys.append(entry)
    data["keys"] = keys
    _write_config_file(config_path, data)
    click.echo(f"Added key {key_id} to {config_path}")


@main.command("remove-key")
@click.option("--config", "config_path", type=click.Path(exists=True, dir_okay=False), required=True)
@click.option("--key-id", type=str, required=True)
def remove_key(config_path: str, key_id: str) -> None:
    """Remove a key from the YAML config."""
    data = _read_config_file(config_path)
    keys = list(data.get("keys", []))
    next_keys = [item for item in keys if not (isinstance(item, dict) and item.get("id") == key_id)]
    if len(next_keys) == len(keys):
        raise click.ClickException(f"Key id not found: {key_id}")
    data["keys"] = next_keys
    _write_config_file(config_path, data)
    click.echo(f"Removed key {key_id} from {config_path}")


@main.command()
@click.option("--config", "config_path", type=click.Path(exists=True, dir_okay=False), required=False)
def metrics(config_path: str | None) -> None:
    """Render Prometheus metrics from the in-process registry."""
    config = load_config(config_path=config_path)
    metrics_registry = Metrics()
    asyncio.run(build_key_pool(config, metrics_registry))
    body, _ = metrics_registry.render()
    click.echo(body.decode("utf-8"))

