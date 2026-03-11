from __future__ import annotations

import json
from pathlib import Path

import pytest
import click
from click.testing import CliRunner

from poolswitch.cli import main as cli
from poolswitch.cli.main import _configure_event_loop_policy, _read_config_file


def _write_config(path: Path) -> None:
    path.write_text(
        """
upstream_base_url: https://example.com
strategy: quota_failover
keys:
  - id: primary
    value: sk-primary
""".strip(),
        encoding="utf-8",
    )


def test_start_invokes_uvicorn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)
    called: dict[str, object] = {}

    def fake_run(app, host, port, log_level, timeout_graceful_shutdown):
        called["host"] = host
        called["port"] = port
        called["log_level"] = log_level
        called["timeout_graceful_shutdown"] = timeout_graceful_shutdown

    monkeypatch.setattr("poolswitch.cli.main.uvicorn.run", fake_run)
    monkeypatch.setattr("poolswitch.cli.main._configure_event_loop_policy", lambda: called.setdefault("configured", True))

    runner = CliRunner()
    result = runner.invoke(cli.main, ["start", "--config", str(config_path), "--listen-port", "9090"])

    assert result.exit_code == 0
    assert called["host"] == "127.0.0.1"
    assert called["port"] == 9090
    assert called["timeout_graceful_shutdown"] == 2
    assert called["configured"] is True


def test_configure_event_loop_policy_noop_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("poolswitch.cli.main.sys.platform", "linux")
    called = {"value": False}
    monkeypatch.setattr("poolswitch.cli.main.asyncio.set_event_loop_policy", lambda _policy: called.__setitem__("value", True))

    _configure_event_loop_policy()

    assert called["value"] is False


def test_configure_event_loop_policy_noop_without_selector(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("poolswitch.cli.main.sys.platform", "win32")
    monkeypatch.delattr("poolswitch.cli.main.asyncio.WindowsSelectorEventLoopPolicy", raising=False)
    called = {"value": False}
    monkeypatch.setattr("poolswitch.cli.main.asyncio.set_event_loop_policy", lambda _policy: called.__setitem__("value", True))

    _configure_event_loop_policy()

    assert called["value"] is False


def test_configure_event_loop_policy_sets_selector_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("poolswitch.cli.main.sys.platform", "win32")

    class DummyPolicy:
        pass

    monkeypatch.setattr("poolswitch.cli.main.asyncio.WindowsSelectorEventLoopPolicy", DummyPolicy, raising=False)
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "poolswitch.cli.main.asyncio.set_event_loop_policy",
        lambda policy: captured.setdefault("policy", policy),
    )

    _configure_event_loop_policy()

    assert isinstance(captured["policy"], DummyPolicy)


def test_status_command(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)

    runner = CliRunner()
    result = runner.invoke(cli.main, ["status", "--config", str(config_path)])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["strategy"] == "quota_failover"
    assert payload["keys"][0]["id"] == "primary"


def test_add_and_remove_key(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)

    runner = CliRunner()
    add_result = runner.invoke(
        cli.main,
        ["add-key", "--config", str(config_path), "--key", "sk-new", "--key-id", "secondary"],
    )
    assert add_result.exit_code == 0

    data = _read_config_file(str(config_path))
    ids = [item["id"] for item in data.get("keys", [])]
    assert ids == ["primary", "secondary"]

    remove_result = runner.invoke(cli.main, ["remove-key", "--config", str(config_path), "--key-id", "secondary"])
    assert remove_result.exit_code == 0

    data = _read_config_file(str(config_path))
    ids = [item["id"] for item in data.get("keys", [])]
    assert ids == ["primary"]


def test_add_key_with_monthly_quota(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)

    runner = CliRunner()
    result = runner.invoke(
        cli.main,
        [
            "add-key",
            "--config",
            str(config_path),
            "--key",
            "sk-billing",
            "--key-id",
            "billing",
            "--monthly-quota",
            "1000",
        ],
    )

    assert result.exit_code == 0
    data = _read_config_file(str(config_path))
    added = next(item for item in data["keys"] if item["id"] == "billing")
    assert added["monthly_quota"] == 1000


def test_add_key_duplicate(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)
    runner = CliRunner()

    result = runner.invoke(
        cli.main,
        ["add-key", "--config", str(config_path), "--key", "sk-primary", "--key-id", "primary"],
    )

    assert result.exit_code != 0
    assert "already exists" in result.output


def test_remove_key_missing(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)
    runner = CliRunner()

    result = runner.invoke(cli.main, ["remove-key", "--config", str(config_path), "--key-id", "missing"])

    assert result.exit_code != 0
    assert "not found" in result.output


def test_metrics_command(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)

    runner = CliRunner()
    result = runner.invoke(cli.main, ["metrics", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "poolswitch_requests_total" in result.output


def test_read_config_requires_mapping(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("- item", encoding="utf-8")

    with pytest.raises(click.ClickException):
        _read_config_file(str(config_path))

