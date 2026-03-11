from pathlib import Path

from poolswitch.config import load_config


def test_load_config_from_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "poolswitch.yaml"
    config_path.write_text(
        """
upstream_base_url: https://api.openai.com
strategy: quota_failover
keys:
  - id: primary
    value: sk-one
  - value: sk-two
storage:
  backend: sqlite
  sqlite_path: runtime.db
        """.strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.upstream_base_url == "https://api.openai.com"
    assert config.storage.backend == "sqlite"
    assert config.key_definitions[0].id == "primary"
    assert config.key_definitions[1].id == "key-2"

