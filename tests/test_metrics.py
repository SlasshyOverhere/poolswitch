from __future__ import annotations

from poolswitch import AppConfig, create_app, load_config
from poolswitch.metrics import Metrics


def test_metrics_render() -> None:
    metrics = Metrics()
    metrics.requests_total.labels(method="GET", path="/", status="200").inc()
    body, content_type = metrics.render()
    assert b"poolswitch_requests_total" in body
    assert "text/plain" in content_type


def test_package_exports() -> None:
    config = AppConfig(upstream_base_url="https://example.com", keys=[{"value": "sk"}])
    assert config.upstream_base_url == "https://example.com"

    # ensure create_app is callable
    app = create_app(config)
    assert app.title == "PoolSwitch Proxy"


def test_load_config_requires_file(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "upstream_base_url: https://example.com\nkeys:\n  - value: sk\n",
        encoding="utf-8",
    )
    config = load_config(config_path)
    assert config.upstream_base_url == "https://example.com"

