from __future__ import annotations

from mailhub.cli import main


def test_init_creates_config_and_state_at_injected_paths(tmp_path, capsys):
    config = tmp_path / "config.toml"
    state = tmp_path / "credentials.json"

    assert main(["init", "--config", str(config), "--state", str(state)]) == 0

    assert config.exists()
    assert state.exists()
    assert "Initialized configuration:" in capsys.readouterr().out


def test_status_reports_configured_accounts_without_provider_calls(tmp_path, capsys):
    config = tmp_path / "config.toml"
    config.write_text("[accounts.home]\nprovider = 'imap'\ncapabilities = ['mail']\n")

    assert main(["status", "--config", str(config)]) == 0

    output = capsys.readouterr().out
    assert '"alias": "home"' in output
    assert '"provider": "imap"' in output


def test_status_reports_missing_configuration_clearly(tmp_path, capsys):
    assert main(["status", "--config", str(tmp_path / "missing.toml")]) == 2
    assert "run 'mailhub init'" in capsys.readouterr().err

