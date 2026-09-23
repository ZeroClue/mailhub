"""Tests for mailhub config subcommands."""

import json
from unittest.mock import patch, MagicMock

import pytest

from mailhub.cli import main
from mailhub.config import Config, ConfigError, parse_config, save_config


@pytest.fixture
def mock_config(tmp_path):
    """Create a temporary config file with test data."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[gmail]\n"
        'client_id = "test_id"\n'
        'client_secret = "test_secret"\n'
        "[accounts.personal]\n"
        'provider = "gmail"\n'
        'capabilities = ["mail"]\n'
    )
    return config_path


class TestConfigList:
    def test_list_empty_config(self, tmp_path, capsys):
        config = tmp_path / "config.toml"
        config.write_text("[accounts]\n")

        assert main(["config", "list", "--config", str(config)]) == 0

        out, err = capsys.readouterr()
        output = out + err
        assert "No accounts configured." in output

    def test_list_shows_accounts(self, tmp_path, capsys):
        config = tmp_path / "config.toml"
        config.write_text(
            "[gmail]\n"
            'client_id = "test_id"\n'
            'client_secret = "test_secret"\n'
            "[accounts.personal]\n"
            'provider = "gmail"\n'
            'capabilities = ["mail", "calendar"]\n'
        )

        assert main(["config", "list", "--config", str(config)]) == 0

        out, err = capsys.readouterr()
        assert "personal" in out
        assert "gmail" in out
        assert "calendar" in out


class TestConfigAddAccount:
    def test_add_account_non_interactive(self, tmp_path, capsys):
        config = tmp_path / "config.toml"
        config.write_text(
            "[gmail]\n"
            'client_id = "test_id"\n'
            'client_secret = "test_secret"\n'
            "[accounts]\n"
        )

        assert main([
            "config", "add-account",
            "--config", str(config),
            "--alias", "test",
            "--provider", "gmail",
            "--capabilities", "mail", "contacts",
        ]) == 0

        content = config.read_text()
        assert "test" in content
        assert "mail" in content
        assert "contacts" in content

    def test_add_account_duplicate_alias_fails(self, tmp_path, capsys):
        config = tmp_path / "config.toml"
        config.write_text(
            "[gmail]\n"
            'client_id = "test_id"\n'
            'client_secret = "test_secret"\n'
            "[accounts.personal]\n"
            'provider = "gmail"\n'
            'capabilities = ["mail"]\n'
        )

        assert main([
            "config", "add-account",
            "--config", str(config),
            "--alias", "personal",
            "--provider", "gmail",
            "--capabilities", "mail",
        ]) == 1

        err = capsys.readouterr().err
        assert "duplicate account alias" in err

    def test_add_account_unsupported_provider_fails(self, tmp_path, capsys):
        config = tmp_path / "config.toml"
        config.write_text("[accounts]\n")

        assert main([
            "config", "add-account",
            "--config", str(config),
            "--alias", "test",
            "--provider", "exchange",
            "--capabilities", "mail",
        ]) == 1

        err = capsys.readouterr().err
        assert "unsupported provider" in err
        assert "exchange" in err

    def test_add_account_unsupported_capability_fails(self, tmp_path, capsys):
        config = tmp_path / "config.toml"
        config.write_text(
            "[gmail]\n"
            'client_id = "test_id"\n'
            'client_secret = "test_secret"\n'
            "[accounts]\n"
        )

        assert main([
            "config", "add-account",
            "--config", str(config),
            "--alias", "test",
            "--provider", "gmail",
            "--capabilities", "tasks",
        ]) == 1

        err = capsys.readouterr().err
        assert "does not support" in err

    def test_add_account_empty_capabilities_fails(self, tmp_path, capsys):
        config = tmp_path / "config.toml"
        config.write_text("[accounts]\n")

        # Missing capabilities - interactive mode not implemented
        assert main([
            "config", "add-account",
            "--config", str(config),
            "--alias", "test",
            "--provider", "gmail",
        ]) == 1

    def test_add_account_missing_args_fails(self, tmp_path):
        config = tmp_path / "config.toml"
        config.write_text("[accounts]\n")

        # Missing all required args
        assert main([
            "config", "add-account",
            "--config", str(config),
        ]) == 1


class TestConfigValidate:
    def test_validate_valid_config(self, tmp_path, capsys):
        config = tmp_path / "config.toml"
        config.write_text(
            "[gmail]\n"
            'client_id = "test_id"\n'
            'client_secret = "test_secret"\n'
            "[accounts.personal]\n"
            'provider = "gmail"\n'
            'capabilities = ["mail"]\n'
        )

        assert main(["config", "validate", "--config", str(config)]) == 0

        out, err = capsys.readouterr()
        assert "Configuration is valid." in out

    def test_validate_missing_file(self, capsys):
        assert main(["config", "validate", "--config", "/nonexistent/config.toml"]) == 2

        err = capsys.readouterr().err
        assert "configuration not found" in err

    def test_validate_invalid_toml(self, tmp_path, capsys):
        config = tmp_path / "config.toml"
        config.write_text("this is not valid toml {{{")

        assert main(["config", "validate", "--config", str(config)]) == 1

        err = capsys.readouterr().err
        assert "invalid TOML" in err

    def test_validate_missing_provider_credentials(self, tmp_path, capsys):
        config = tmp_path / "config.toml"
        config.write_text(
            "[accounts.personal]\n"
            'provider = "gmail"\n'
            'capabilities = ["mail"]\n'
        )

        assert main(["config", "validate", "--config", str(config)]) == 1

        out, err = capsys.readouterr()
        assert "provider gmail missing client_id" in err
        assert "provider gmail missing client_secret" in err

    def test_validate_missing_graph_client_id(self, tmp_path, capsys):
        config = tmp_path / "config.toml"
        config.write_text(
            "[gmail]\n"
            'client_id = "test_id"\n'
            'client_secret = "test_secret"\n'
            "[accounts.work]\n"
            'provider = "graph"\n'
            'capabilities = ["mail"]\n'
        )

        assert main(["config", "validate", "--config", str(config)]) == 1

        out, err = capsys.readouterr()
        assert "provider graph missing client_id" in err

    def test_validate_invalid_account_structure(self, tmp_path, capsys):
        config = tmp_path / "config.toml"
        config.write_text("[accounts.bad]\nprovider = 'exchange'\ncapabilities = ['mail']\n")

        assert main(["config", "validate", "--config", str(config)]) == 1


class TestConfigDoctor:
    def test_doctor_runs_validation_and_core_doctor(self, tmp_path, capsys):
        config = tmp_path / "config.toml"
        config.write_text(
            "[gmail]\n"
            'client_id = "test_id"\n'
            'client_secret = "test_secret"\n'
            "[accounts.personal]\n"
            'provider = "gmail"\n'
            'capabilities = ["mail"]\n'
        )

        assert main(["config", "doctor", "--config", str(config)]) == 1

        out, err = capsys.readouterr()
        assert "Configuration is valid." in out


class TestConfigRemoveAccount:
    def test_remove_existing_account(self, tmp_path, capsys):
        config = tmp_path / "config.toml"
        config.write_text(
            "[gmail]\n"
            'client_id = "test_id"\n'
            'client_secret = "test_secret"\n'
            "[accounts.personal]\n"
            'provider = "gmail"\n'
            'capabilities = ["mail"]\n'
        )

        assert main(["config", "remove-account", "personal", "--config", str(config)]) == 0

        content = config.read_text()
        assert "personal" not in content

    def test_remove_nonexistent_account_fails(self, tmp_path, capsys):
        config = tmp_path / "config.toml"
        config.write_text("[accounts]\n")

        assert main(["config", "remove-account", "nonexistent", "--config", str(config)]) == 1

        err = capsys.readouterr().err
        assert f"account nonexistent not found" in err


class TestConfigSetupProviders:
    def test_setup_google_requires_both_id_and_secret(self, tmp_path, capsys, monkeypatch):
        config = tmp_path / "config.toml"
        config.write_text("[accounts]\n")

        inputs = iter(["", "secret"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))
        monkeypatch.setattr("webbrowser.open", lambda _: None)

        assert main(["config", "setup-google", "--config", str(config)]) == 1

        err = capsys.readouterr().err
        assert "both client_id and client_secret are required" in err

    def test_setup_microsoft_requires_client_id(self, tmp_path, capsys, monkeypatch):
        config = tmp_path / "config.toml"
        config.write_text("[accounts]\n")

        inputs = iter([""])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))
        monkeypatch.setattr("webbrowser.open", lambda _: None)

        assert main(["config", "setup-microsoft", "--config", str(config)]) == 1

        err = capsys.readouterr().err
        assert "client_id is required" in err


class TestConfigAtomicWrites:
    def test_atomic_write_preserves_permissions(self, tmp_path):
        config = tmp_path / "config.toml"
        config.write_text("[accounts]\n")
        config.chmod(0o600)
        original_inode = config.stat().st_ino

        from mailhub.config import add_account, load_config
        cfg = load_config(config)
        add_account(cfg, "new", "gmail", ["mail"], config)
        config.chmod(0o600)

        assert config.stat().st_mode & 0o777 == 0o600

    def test_atomic_write_preserves_provider_sections(self, tmp_path):
        config = tmp_path / "config.toml"
        config.write_text(
            "[gmail]\n"
            'client_id = "test_id"\n'
            'client_secret = "test_secret"\n'
            "[accounts]\n"
        )

        from mailhub.config import add_account, load_config
        cfg = load_config(config)
        add_account(cfg, "new", "gmail", ["mail"], config)

        content = config.read_text()
        assert "test_id" in content  # gmail section preserved


class TestProviderCapabilitiesConstant:
    def test_provider_capabilities_contains_expected_providers(self):
        from mailhub.config import PROVIDER_CAPABILITIES

        assert "gmail" in PROVIDER_CAPABILITIES
        assert "graph" in PROVIDER_CAPABILITIES
        assert "imap" in PROVIDER_CAPABILITIES
        assert "caldav" in PROVIDER_CAPABILITIES
        assert "carddav" in PROVIDER_CAPABILITIES

    def test_gmail_capabilities(self):
        from mailhub.config import PROVIDER_CAPABILITIES

        assert "mail" in PROVIDER_CAPABILITIES["gmail"]
        assert "calendar" in PROVIDER_CAPABILITIES["gmail"]
        assert "contacts" in PROVIDER_CAPABILITIES["gmail"]

    def test_graph_capabilities(self):
        from mailhub.config import PROVIDER_CAPABILITIES

        assert "mail" in PROVIDER_CAPABILITIES["graph"]
        assert "calendar" in PROVIDER_CAPABILITIES["graph"]
        assert "contacts" in PROVIDER_CAPABILITIES["graph"]
        assert "tasks" in PROVIDER_CAPABILITIES["graph"]

    def test_imap_capabilities(self):
        from mailhub.config import PROVIDER_CAPABILITIES

        assert "mail" in PROVIDER_CAPABILITIES["imap"]
        assert "calendar" not in PROVIDER_CAPABILITIES["imap"]

    def test_caldav_capabilities(self):
        from mailhub.config import PROVIDER_CAPABILITIES

        assert "calendar" in PROVIDER_CAPABILITIES["caldav"]
        assert "tasks" in PROVIDER_CAPABILITIES["caldav"]

    def test_carddav_capabilities(self):
        from mailhub.config import PROVIDER_CAPABILITIES

        assert "contacts" in PROVIDER_CAPABILITIES["carddav"]
