"""Owner-only, atomically persisted credential-state primitives."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

try:  # fcntl is available on Mailhub's supported Unix-like local targets.
    import fcntl
except ImportError:  # pragma: no cover - explicit failure is clearer on unsupported hosts.
    fcntl = None  # type: ignore[assignment]


class StoreError(ValueError):
    """Raised when credential state is malformed or cannot be safely used."""


def state_path(base: Path | None = None) -> Path:
    """Return the XDG state location, optionally rooted at *base*."""
    if base is not None:
        return base / "mailhub" / "credentials.json"
    root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return root / "mailhub" / "credentials.json"


class CredentialStore:
    """A small JSON state store with atomic writes and a process-wide lock."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or state_path()
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def initialize(self) -> Path:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.path.parent, stat.S_IRWXU)
        if not self.path.exists():
            self.save({})
        else:
            os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)
        return self.path

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Lock a complete read/refresh/write transaction across local processes."""
        if fcntl is None:
            raise StoreError("credential locking requires a Unix-like platform")
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.path.parent, stat.S_IRWXU)
        descriptor = os.open(self.lock_path, os.O_WRONLY | os.O_CREAT, 0o600)
        try:
            os.chmod(self.lock_path, stat.S_IRUSR | stat.S_IWUSR)
            with os.fdopen(descriptor, "w") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                yield
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except Exception:
            # fdopen owns descriptor if entered; only close manually before that.
            raise

    def load(self) -> dict[str, Any]:
        try:
            with self.path.open(encoding="utf-8") as file:
                data = json.load(file)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError as error:
            raise StoreError(f"credential state is invalid JSON: {self.path}") from error
        if not isinstance(data, dict):
            raise StoreError("credential state root must be an object")
        return data

    def save(self, data: dict[str, Any]) -> None:
        """Replace credential state atomically with an owner-only file."""
        if not isinstance(data, dict):
            raise StoreError("credential state must be an object")
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.path.parent, stat.S_IRWXU)
        descriptor, temporary_name = tempfile.mkstemp(prefix=".credentials-", dir=self.path.parent)
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, stat.S_IRUSR | stat.S_IWUSR)
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(data, file, sort_keys=True, separators=(",", ":"))
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
            os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)
        finally:
            if temporary.exists():
                temporary.unlink()
