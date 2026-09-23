"""Tests for mailhub.backup module."""

from __future__ import annotations

import json
import tarfile
import warnings
from pathlib import Path

import pytest

from mailhub.backup import (
    backup_all,
    backup_audit,
    backup_config,
    backup_state,
    restore_audit,
    restore_config,
    restore_state,
)
from mailhub.config import initialize_config
from mailhub.store import CredentialStore, state_path


def test_backup_config_copies_file(tmp_path: Path) -> None:
    # Create a config file
    config_dir = tmp_path / "config"
    config_file = initialize_config(config_dir / "config.toml")
    config_file.write_text("[accounts.test]\nprovider = \"gmail\"\ncapabilities = [\"mail\"]\n")

    # Backup
    output = tmp_path / "backup" / "config.toml"
    backup_config(output, config_file)

    assert output.exists()
    assert output.read_text() == config_file.read_text()
    # Check permissions (0600)
    assert output.stat().st_mode & 0o777 == 0o600
    assert output.parent.stat().st_mode & 0o777 == 0o700


def test_backup_config_missing_raises(tmp_path: Path) -> None:
    missing = tmp_path / "missing.toml"
    with pytest.raises(FileNotFoundError):
        backup_config(tmp_path / "out.toml", missing)


def test_backup_state_copies_file_and_warns(tmp_path: Path) -> None:
    # Create a state file with secrets
    state_dir = tmp_path / "state"
    store = CredentialStore(state_dir / "credentials.json")
    store.initialize()
    store.save({
        "accounts": {
            "test": {
                "access_token": "access-secret",
                "refresh_token": "refresh-secret",
                "expires_at": 9999999999,
                "client_id": "client-id",
                "client_secret": "client-secret",
            }
        }
    })

    # Backup - should warn about secrets
    output = tmp_path / "backup" / "credentials.json"
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        backup_state(output, store.path)
        assert len(w) == 1
        assert "secrets" in str(w[0].message).lower()

    assert output.exists()
    data = json.loads(output.read_text())
    assert data["accounts"]["test"]["refresh_token"] == "refresh-secret"
    assert output.stat().st_mode & 0o777 == 0o600
    assert output.parent.stat().st_mode & 0o777 == 0o700


def test_backup_state_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        backup_state(tmp_path / "out.json", tmp_path / "missing.json")


def test_backup_audit_copies_file(tmp_path: Path) -> None:
    # Create audit file
    audit_file = tmp_path / "audit.jsonl"
    audit_file.write_text('{"timestamp": "2025-01-01T00:00:00Z", "account": "test", "operation": "send", "details": {}}\n')

    output = tmp_path / "backup" / "audit.jsonl"
    backup_audit(output, audit_file)

    assert output.exists()
    assert output.read_text() == audit_file.read_text()
    assert output.stat().st_mode & 0o777 == 0o600


def test_backup_audit_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        backup_audit(tmp_path / "out.jsonl", tmp_path / "missing.jsonl")


def test_backup_all_creates_timestamped_archive(tmp_path: Path) -> None:
    # Setup config, state, audit
    config_dir = tmp_path / "config"
    config_file = initialize_config(config_dir / "config.toml")
    config_file.write_text("[accounts.test]\nprovider = \"gmail\"\ncapabilities = [\"mail\"]\n")

    state_dir = tmp_path / "state"
    store = CredentialStore(state_dir / "credentials.json")
    store.initialize()
    store.save({"accounts": {"test": {"refresh_token": "secret"}}})

    audit_file = state_dir / "audit.jsonl"
    audit_file.write_text('{"timestamp": "2025-01-01T00:00:00Z", "account": "test", "operation": "send", "details": {}}\n')

    # Backup all
    output_dir = tmp_path / "backups"
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        archive = backup_all(output_dir, config_file, store.path)
        assert len(w) == 1
        assert "secrets" in str(w[0].message).lower()

    assert archive.exists()
    assert archive.name.startswith("mailhub-backup-")
    assert archive.name.endswith(".tar.gz")
    assert archive.stat().st_mode & 0o777 == 0o600
    assert output_dir.stat().st_mode & 0o777 == 0o700

    # Verify archive contents
    with tarfile.open(archive, "r:gz") as tar:
        names = tar.getnames()
        assert "config.toml" in names
        assert "credentials.json" in names
        assert "audit.jsonl" in names


def test_backup_all_partial_sources(tmp_path: Path) -> None:
    # Only config exists
    config_dir = tmp_path / "config"
    config_file = initialize_config(config_dir / "config.toml")
    config_file.write_text("[accounts.test]\nprovider = \"gmail\"\ncapabilities = [\"mail\"]\n")

    output_dir = tmp_path / "backups"
    with warnings.catch_warnings():
        warnings.simplefilter("always")
        archive = backup_all(output_dir, config_file, tmp_path / "nonexistent.json")

    assert archive.exists()
    with tarfile.open(archive, "r:gz") as tar:
        names = tar.getnames()
        assert "config.toml" in names
        assert "credentials.json" not in names
        assert "audit.jsonl" not in names


def test_restore_config_validates_toml(tmp_path: Path) -> None:
    # Valid config
    valid = tmp_path / "valid.toml"
    valid.write_text("[accounts.test]\nprovider = \"gmail\"\ncapabilities = [\"mail\"]\n")

    dest = tmp_path / "restored" / "config.toml"
    restore_config(valid, dest)

    assert dest.exists()
    assert dest.read_text() == valid.read_text()
    assert dest.stat().st_mode & 0o777 == 0o600


def test_restore_config_invalid_toml_raises(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.toml"
    invalid.write_text("not valid toml [[[")

    with pytest.raises(ValueError, match="Invalid config backup"):
        restore_config(invalid, tmp_path / "dest.toml")


def test_restore_config_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        restore_config(tmp_path / "missing.toml", tmp_path / "dest.toml")


def test_restore_state_atomic_write_via_credentialstore(tmp_path: Path) -> None:
    # Create a backup file
    backup = tmp_path / "backup.json"
    backup.write_text(json.dumps({
        "accounts": {
            "test": {
                "access_token": "access",
                "refresh_token": "refresh",
                "expires_at": 1234567890,
                "client_id": "id",
                "client_secret": "secret",
            }
        }
    }))

    dest = tmp_path / "state" / "credentials.json"
    restore_state(backup, dest)

    assert dest.exists()
    data = json.loads(dest.read_text())
    assert data["accounts"]["test"]["refresh_token"] == "refresh"
    assert dest.stat().st_mode & 0o777 == 0o600
    assert dest.parent.stat().st_mode & 0o777 == 0o700


def test_restore_state_invalid_json_raises(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not json")

    with pytest.raises(ValueError, match="not JSON"):
        restore_state(invalid, tmp_path / "dest.json")


def test_restore_state_wrong_structure_raises(tmp_path: Path) -> None:
    # Root is not an object
    invalid = tmp_path / "invalid.json"
    invalid.write_text('["not", "an", "object"]')

    with pytest.raises(ValueError, match="root must be an object"):
        restore_state(invalid, tmp_path / "dest.json")

    # Accounts is not an object
    invalid2 = tmp_path / "invalid2.json"
    invalid2.write_text('{"accounts": "not-an-object"}')

    with pytest.raises(ValueError, match="accounts.*must be an object"):
        restore_state(invalid2, tmp_path / "dest2.json")


def test_restore_state_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        restore_state(tmp_path / "missing.json", tmp_path / "dest.json")


def test_restore_audit_validates_jsonl(tmp_path: Path) -> None:
    valid = tmp_path / "valid.jsonl"
    valid.write_text(
        '{"timestamp": "2025-01-01T00:00:00Z", "account": "test", "operation": "send", "details": {}}\n'
        '{"timestamp": "2025-01-01T00:00:01Z", "account": "test", "operation": "move", "details": {}}\n'
    )

    dest = tmp_path / "restored" / "audit.jsonl"
    restore_audit(valid, dest)

    assert dest.exists()
    assert dest.read_text() == valid.read_text()
    assert dest.stat().st_mode & 0o777 == 0o600


def test_restore_audit_invalid_jsonl_raises(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.jsonl"
    invalid.write_text(
        '{"valid": "line"}\n'
        'not json\n'
        '{"another": "line"}\n'
    )

    with pytest.raises(ValueError, match="line 2"):
        restore_audit(invalid, tmp_path / "dest.jsonl")


def test_restore_audit_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        restore_audit(tmp_path / "missing.jsonl", tmp_path / "dest.jsonl")


def test_owner_only_permissions_on_backup_outputs(tmp_path: Path) -> None:
    # Setup minimal sources
    config_dir = tmp_path / "config"
    config_file = initialize_config(config_dir / "config.toml")
    config_file.write_text("[accounts.test]\nprovider = \"gmail\"\ncapabilities = [\"mail\"]\n")

    state_dir = tmp_path / "state"
    store = CredentialStore(state_dir / "credentials.json")
    store.initialize()
    store.save({"accounts": {}})

    audit_file = state_dir / "audit.jsonl"
    audit_file.write_text("")

    # Track backup output paths
    backup_outputs = [
        tmp_path / "out" / "config.toml",
        tmp_path / "out" / "credentials.json",
        tmp_path / "out" / "audit.jsonl",
    ]

    # Run all backup functions
    backup_config(backup_outputs[0], config_file)
    backup_state(backup_outputs[1], store.path)
    backup_audit(backup_outputs[2], audit_file)

    archive = backup_all(tmp_path / "archives", config_file, store.path)
    backup_outputs.append(archive)

    # Check all backup outputs have 0600, their parent dirs 0700
    for file in backup_outputs:
        assert file.exists(), f"{file} not created"
        assert file.stat().st_mode & 0o777 == 0o600, f"{file} not 0600"
        assert file.parent.stat().st_mode & 0o777 == 0o700, f"{file.parent} not 0700"
