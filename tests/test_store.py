from __future__ import annotations

import json
import os

from mailhub.store import CredentialStore, state_path


def test_state_path_uses_injected_base(tmp_path):
    assert state_path(tmp_path) == tmp_path / "mailhub" / "credentials.json"


def test_initialize_creates_owner_only_state_file(tmp_path):
    path = tmp_path / "state" / "credentials.json"

    CredentialStore(path).initialize()

    assert json.loads(path.read_text()) == {}
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700


def test_save_replaces_state_atomically_and_preserves_permissions(tmp_path):
    path = tmp_path / "credentials.json"
    store = CredentialStore(path)
    store.initialize()
    original_inode = path.stat().st_ino

    store.save({"accounts": {"work": {"refresh_token": "not-printed"}}})

    assert store.load() == {"accounts": {"work": {"refresh_token": "not-printed"}}}
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.stat().st_ino != original_inode
    assert not list(tmp_path.glob(".credentials-*"))


def test_transaction_provides_lock_file_with_private_permissions(tmp_path):
    store = CredentialStore(tmp_path / "credentials.json")

    with store.transaction():
        store.save({"version": 1})

    assert store.load() == {"version": 1}
    assert store.lock_path.stat().st_mode & 0o777 == 0o600
    assert os.path.exists(store.lock_path)
