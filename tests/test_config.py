from __future__ import annotations

import pytest

from mailhub.config import ConfigError, config_path, initialize_config, load_config, parse_config


def test_config_path_uses_injected_base(tmp_path):
    assert config_path(tmp_path) == tmp_path / "mailhub" / "config.toml"


def test_initialize_config_creates_owner_only_template(tmp_path):
    path = tmp_path / "config" / "mailhub" / "config.toml"

    initialize_config(path)

    assert path.exists()
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert "[accounts.personal]" in path.read_text()


def test_load_config_accepts_supported_provider_capabilities(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        "[accounts.personal]\nprovider = 'graph'\ncapabilities = ['mail', 'calendar', 'tasks']\n"
    )

    config = load_config(path)

    assert config.account("personal").provider == "graph"
    assert config.account("personal").capabilities == frozenset({"mail", "calendar", "tasks"})


def test_config_rejects_unsupported_provider_capability():
    with pytest.raises(ConfigError, match="does not support: tasks"):
        parse_config({"accounts": {"inbox": {"provider": "imap", "capabilities": ["mail", "tasks"]}}})


def test_config_rejects_unknown_provider():
    with pytest.raises(ConfigError, match="unsupported provider"):
        parse_config({"accounts": {"inbox": {"provider": "exchange", "capabilities": ["mail"]}}})


def test_config_rejects_empty_capabilities():
    with pytest.raises(ConfigError, match="non-empty array"):
        parse_config({"accounts": {"inbox": {"provider": "gmail", "capabilities": []}}})
