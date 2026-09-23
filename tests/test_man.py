"""Tests for man pages."""

import subprocess
from pathlib import Path


MAN_DIR = Path(__file__).parent.parent / "docs" / "man"


def test_man_pages_exist():
    """Verify man page files exist."""
    mailhub_man = MAN_DIR / "mailhub.1"
    mail_man = MAN_DIR / "mail.1"
    
    assert mailhub_man.exists(), f"Missing: {mailhub_man}"
    assert mail_man.exists(), f"Missing: {mail_man}"


def test_mailhub_man_has_required_sections():
    """Verify mailhub.1 has all required sections."""
    content = (MAN_DIR / "mailhub.1").read_text()
    
    required_sections = [
        '.SH NAME',
        '.SH SYNOPSIS',
        '.SH DESCRIPTION',
        '.SH OPTIONS',
        '.SH COMMANDS',
        '.SH CONFIG SUBCOMMANDS',
        '.SH FILES',
        '.SH EXAMPLES',
        '.SH SEE ALSO',
    ]
    
    for section in required_sections:
        assert section in content, f"Missing section: {section}"


def test_mail_man_has_required_sections():
    """Verify mail.1 has all required sections."""
    content = (MAN_DIR / "mail.1").read_text()
    
    required_sections = [
        '.SH NAME',
        '.SH SYNOPSIS',
        '.SH DESCRIPTION',
        '.SH OPTIONS',
        '.SH COMMANDS',
        '.SH FILES',
        '.SH EXAMPLES',
        '.SH SEE ALSO',
    ]
    
    for section in required_sections:
        assert section in content, f"Missing section: {section}"


def test_mailhub_man_th_macro():
    """Verify mailhub.1 has correct .TH macro."""
    mailhub_content = (MAN_DIR / "mailhub.1").read_text()
    assert '.TH MAILHUB 1' in mailhub_content, "mailhub.1 missing correct .TH macro"
    assert '"2026-09-22"' in mailhub_content, "mailhub.1 missing date"
    assert '"Mailhub 0.1.0"' in mailhub_content, "mailhub.1 missing version"
    assert '"User Commands"' in mailhub_content, "mailhub.1 missing section"


def test_mail_man_th_macro():
    """Verify mail.1 has correct .TH macro."""
    mail_content = (MAN_DIR / "mail.1").read_text()
    assert '.TH MAIL 1' in mail_content, "mail.1 missing correct .TH macro"
    assert '"2026-09-22"' in mail_content, "mail.1 missing date"
    assert '"Mailhub 0.1.0"' in mail_content, "mail.1 missing version"
    assert '"User Commands"' in mail_content, "mail.1 missing section"


def test_man_pages_render_without_errors():
    """Verify man pages render with man -l without errors."""
    for man_file in ["mailhub.1", "mail.1"]:
        result = subprocess.run(
            ["man", "-l", str(MAN_DIR / man_file)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"man -l failed for {man_file}: {result.stderr}"
        # Check output contains expected command name
        assert man_file.replace('.1', '').upper() in result.stdout.upper(), \
            f"Output doesn't contain command name for {man_file}"


def test_mailhub_man_content():
    """Verify mailhub.1 contains key commands."""
    content = (MAN_DIR / "mailhub.1").read_text()
    
    key_commands = [
        'init', 'auth', 'status', 'doctor', 'reauth', 'logout',
        'serve', 'mcp', 'config'
    ]
    
    for cmd in key_commands:
        assert cmd in content, f"Missing command {cmd} in mailhub.1"
    
    # Check config subcommands
    config_subcommands = [
        'list', 'add-account', 'validate', 'doctor',
        'setup-google', 'setup-microsoft', 'remove-account'
    ]
    
    for subcmd in config_subcommands:
        assert subcmd in content, f"Missing config subcommand {subcmd} in mailhub.1"


def test_mail_man_content():
    """Verify mail.1 contains key commands and options."""
    content = (MAN_DIR / "mail.1").read_text()
    
    key_commands = [
        'accounts', 'folders', 'search', 'get', 'send', 'draft'
    ]
    
    for cmd in key_commands:
        assert cmd in content, f"Missing command {cmd} in mail.1"
    
    key_options = [
        '--url', '--token', '--ro', '--json', '--confirm', '--config', '--state'
    ]
    
    for opt in key_options:
        assert opt in content, f"Missing option {opt} in mail.1"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
