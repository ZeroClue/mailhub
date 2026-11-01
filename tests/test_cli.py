from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import mailhub.cli as cli
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


def test_imap_oauth_auth_command_requests_provider_scope(tmp_path, monkeypatch, capsys):
    config = tmp_path / "config.toml"
    config.write_text(
        '[graph]\nclient_id = "entra-client"\n\n'
        "[accounts.outlook]\n"
        'provider = "imap"\n'
        'capabilities = ["mail"]\n'
        'email = "user@outlook.com"\n'
        'imap_host = "imap-mail.outlook.com"\n'
        'smtp_host = "smtp-mail.outlook.com"\n'
        "imap_port = 993\n"
        "smtp_port = 587\n"
        'auth_method = "oauth2"\n'
    )
    state = tmp_path / "state" / "credentials.json"
    monkeypatch.setattr(cli, "state_path", lambda: state)

    assert main(["auth", "imap", "outlook", "--config", str(config)]) == 0

    output = capsys.readouterr().out
    auth_url = next(
        line for line in output.splitlines() if "login.microsoftonline.com" in line
    )
    scopes = parse_qs(urlparse(auth_url).query)["scope"][0].split()
    assert "https://outlook.office.com/IMAP.AccessAsUser.All" in scopes
    assert "https://outlook.office.com/SMTP.Send" in scopes
    assert "offline_access" in scopes
    assert "mailhub auth imap outlook --code" in output
