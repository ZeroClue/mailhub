"""Backup and restore utilities for Mailhub configuration, state, and audit log."""

from __future__ import annotations

import json
import os
import shutil
import stat
import tarfile
import tempfile
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import config_path, load_config
from .store import CredentialStore, state_path


__all__ = [
    "backup_config",
    "backup_state",
    "backup_audit",
    "backup_all",
    "restore_config",
    "restore_state",
    "restore_audit",
]


def _owner_only_permissions(path: Path) -> None:
    """Set owner-only permissions (0600) on a file."""
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def _owner_only_dir(path: Path) -> None:
    """Set owner-only permissions (0700) on a directory."""
    path.chmod(stat.S_IRWXU)


def backup_config(output_path: Path, config_file: Path | None = None) -> Path:
    """
    Export config.toml (no secrets) to output_path.

    Args:
        output_path: Destination file path for the config backup.
        config_file: Optional explicit config file path. Defaults to XDG config.

    Returns:
        The output_path that was written.

    Raises:
        FileNotFoundError: If the config file doesn't exist.
    """
    src = config_file or config_path()
    if not src.exists():
        raise FileNotFoundError(f"Configuration not found: {src}")

    output_path = Path(output_path)
    output_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _owner_only_dir(output_path.parent)

    # Read and write config without any modification (no secrets in config.toml)
    shutil.copy2(src, output_path)
    _owner_only_permissions(output_path)
    return output_path


def backup_state(output_path: Path, state_file: Path | None = None) -> Path:
    """
    Export credentials.json (WITH secrets) to output_path.

    WARNING: The output file contains OAuth refresh tokens and client secrets.
    Handle with extreme care. Set restrictive permissions (0600) and do not
    store in synced/cloud directories.

    Args:
        output_path: Destination file path for the state backup.
        state_file: Optional explicit state file path. Defaults to XDG state.

    Returns:
        The output_path that was written.

    Raises:
        FileNotFoundError: If the state file doesn't exist.
    """
    src = state_file or state_path()
    if not src.exists():
        raise FileNotFoundError(f"Credential state not found: {src}")

    output_path = Path(output_path)
    output_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _owner_only_dir(output_path.parent)

    # Copy with owner-only permissions
    shutil.copy2(src, output_path)
    _owner_only_permissions(output_path)

    # Emit a warning to the caller (not logged)
    warnings.warn(
        f"State backup written to {output_path} contains secrets (refresh tokens, client secrets). "
        f"Store securely and do not commit to version control.",
        UserWarning,
        stacklevel=2,
    )
    return output_path


def backup_audit(output_path: Path, audit_file: Path | None = None) -> Path:
    """
    Export audit.jsonl to output_path.

    Args:
        output_path: Destination file path for the audit backup.
        audit_file: Optional explicit audit file path. Defaults to XDG state dir.

    Returns:
        The output_path that was written.

    Raises:
        FileNotFoundError: If the audit file doesn't exist.
    """
    if audit_file is None:
        audit_file = state_path().parent / "audit.jsonl"

    if not audit_file.exists():
        raise FileNotFoundError(f"Audit log not found: {audit_file}")

    output_path = Path(output_path)
    output_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _owner_only_dir(output_path.parent)

    # Copy with owner-only permissions
    shutil.copy2(audit_file, output_path)
    _owner_only_permissions(output_path)
    return output_path


def backup_all(output_dir: Path, config_file: Path | None = None, state_file: Path | None = None) -> Path:
    """
    Create a timestamped tar.gz archive containing config, state, and audit.

    Args:
        output_dir: Directory where the archive will be created.
        config_file: Optional explicit config file path.
        state_file: Optional explicit state file path.

    Returns:
        Path to the created archive.

    Raises:
        FileNotFoundError: If any source file is missing.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    _owner_only_dir(output_dir)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_name = f"mailhub-backup-{timestamp}.tar.gz"
    archive_path = output_dir / archive_name

    # Create a temporary directory for staging
    with tempfile.TemporaryDirectory(prefix="mailhub-backup-") as tmpdir:
        tmp = Path(tmpdir)

        # Stage config
        config_src = config_file or config_path()
        if config_src.exists():
            shutil.copy2(config_src, tmp / "config.toml")

        # Stage state
        state_src = state_file or state_path()
        if state_src.exists():
            shutil.copy2(state_src, tmp / "credentials.json")

        # Stage audit
        audit_src = (state_file or state_path()).parent / "audit.jsonl"
        if audit_src.exists():
            shutil.copy2(audit_src, tmp / "audit.jsonl")

        # Create tar.gz archive
        with tarfile.open(archive_path, "w:gz") as tar:
            for item in tmp.iterdir():
                tar.add(item, arcname=item.name)

    _owner_only_permissions(archive_path)

    # Warn about secrets in archive
    warnings.warn(
        f"Backup archive {archive_path} contains credentials.json with secrets. "
        f"Store securely and do not commit to version control.",
        UserWarning,
        stacklevel=2,
    )

    return archive_path


def restore_config(input_path: Path, config_file: Path | None = None) -> Path:
    """
    Import config.toml from input_path.

    Args:
        input_path: Source backup file path.
        config_file: Optional explicit config file path. Defaults to XDG config.

    Returns:
        The config_file that was written.

    Raises:
        FileNotFoundError: If the input file doesn't exist.
        ValueError: If the input is not valid TOML config.
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Backup file not found: {input_path}")

    dest = config_file or config_path()
    dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _owner_only_dir(dest.parent)

    # Validate it's valid TOML by loading it
    try:
        load_config(input_path)
    except Exception as e:
        raise ValueError(f"Invalid config backup: {e}") from e

    shutil.copy2(input_path, dest)
    _owner_only_permissions(dest)
    return dest


def restore_state(input_path: Path, state_file: Path | None = None) -> Path:
    """
    Import credentials.json from input_path using atomic write via CredentialStore.

    Args:
        input_path: Source backup file path (contains secrets).
        state_file: Optional explicit state file path. Defaults to XDG state.

    Returns:
        The state_file that was written.

    Raises:
        FileNotFoundError: If the input file doesn't exist.
        ValueError: If the input is not valid JSON or has wrong structure.
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Backup file not found: {input_path}")

    dest = state_file or state_path()

    # Load and validate the backup
    try:
        with input_path.open(encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid state backup (not JSON): {e}") from e

    if not isinstance(data, dict):
        raise ValueError("State backup root must be an object")

    # Validate structure (accounts dict with string keys)
    if "accounts" in data and not isinstance(data["accounts"], dict):
        raise ValueError("State backup 'accounts' must be an object")

    # Use CredentialStore for atomic write with correct permissions
    store = CredentialStore(dest)
    store.initialize()
    store.save(data)

    # Ensure permissions are correct
    _owner_only_permissions(dest)
    _owner_only_dir(dest.parent)

    return dest


def restore_audit(input_path: Path, audit_file: Path | None = None) -> Path:
    """
    Import audit.jsonl from input_path.

    Args:
        input_path: Source backup file path.
        audit_file: Optional explicit audit file path. Defaults to XDG state dir.

    Returns:
        The audit_file that was written.

    Raises:
        FileNotFoundError: If the input file doesn't exist.
        ValueError: If the input is not valid JSONL.
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Backup file not found: {input_path}")

    if audit_file is None:
        audit_file = (state_path()).parent / "audit.jsonl"

    audit_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _owner_only_dir(audit_file.parent)

    # Validate each line is valid JSON
    try:
        with input_path.open(encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line:
                    json.loads(line)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid audit backup at line {line_num}: {e}") from e

    shutil.copy2(input_path, audit_file)
    _owner_only_permissions(audit_file)
    return audit_file
