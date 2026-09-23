"""Tests for mailhub completion module."""

import pytest

from mailhub.completion import (
    CONFIG_SUBCOMMANDS,
    MAILHUB_SUBCOMMANDS,
    MAIL_SUBCOMMANDS,
    generate_bash_completion,
    generate_fish_completion,
    generate_zsh_completion,
    generate_completion,
)


class TestGenerateCompletion:
    def test_bash_includes_subcommands(self):
        script = generate_bash_completion()
        for cmd in ("init", "auth", "status", "doctor", "config", "mcp"):
            assert cmd in script
        assert "complete -F _mailhub mailhub" in script

    def test_bash_includes_config_and_mail_subcommands(self):
        script = generate_bash_completion()
        for sub in ("add-account", "setup-google", "setup-microsoft"):
            assert sub in script
        for sub in ("send", "search", "get", "folders"):
            assert sub in script

    def test_zsh_includes_subcommands(self):
        script = generate_zsh_completion()
        for cmd in ("init", "auth", "status", "doctor", "config", "mcp"):
            assert cmd in script
        assert "compdef" in script

    def test_fish_includes_subcommands(self):
        script = generate_fish_completion()
        for cmd in ("init", "auth", "status", "doctor", "config", "mcp"):
            assert cmd in script
        assert "complete -c mailhub" in script

    def test_generate_completion_dispatch(self):
        assert generate_completion("bash") == generate_bash_completion()
        assert generate_completion("zsh") == generate_zsh_completion()
        assert generate_completion("fish") == generate_fish_completion()

    def test_generate_completion_invalid_shell(self):
        with pytest.raises(ValueError, match="Unsupported shell"):
            generate_completion("powershell")


class TestCompletionConstants:
    def test_mailhub_subcommands(self):
        assert "config" in MAILHUB_SUBCOMMANDS
        assert "mcp" in MAILHUB_SUBCOMMANDS

    def test_config_subcommands(self):
        assert "setup-google" in CONFIG_SUBCOMMANDS
        assert "setup-microsoft" in CONFIG_SUBCOMMANDS

    def test_mail_subcommands(self):
        assert "send" in MAIL_SUBCOMMANDS
        assert "draft" in MAIL_SUBCOMMANDS


class TestCompletionCLI:
    def test_cli_generates_bash(self, capsys):
        from mailhub.cli import main
        assert main(["--generate-completion", "bash"]) == 0
        out = capsys.readouterr().out
        assert "# mailhub bash completion" in out
        assert "complete -F _mailhub mailhub" in out

    def test_cli_generates_fish(self, capsys):
        from mailhub.cli import main
        assert main(["--generate-completion", "fish"]) == 0
        out = capsys.readouterr().out
        assert "# mailhub fish completion" in out
        assert "complete -c mailhub" in out

    def test_cli_invalid_shell(self, capsys):
        from mailhub.cli import main
        with pytest.raises(SystemExit) as exc:
            main(["--generate-completion", "powershell"])
        assert exc.value.code == 2  # argparse rejects invalid choice
