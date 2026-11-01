"""Unit tests for mailhub.mcp module."""

from __future__ import annotations

import pytest

from mailhub.core import Core
from mailhub import mcp
from mailhub.mcp import FULL_TOOL_NAMES, READ_ONLY_TOOL_NAMES, create_server


def test_read_only_server_registers_only_status_tool():
    server = create_server()

    # FastMCP retains registrations in its tool manager; M1 must have no mutation tools.
    registered = set(server._tool_manager._tools)
    assert registered == set(READ_ONLY_TOOL_NAMES)


def test_full_mode_registers_mutation_tools():
    server = create_server(mode="full")

    registered = set(server._tool_manager._tools)
    assert registered == set(FULL_TOOL_NAMES)


def test_invalid_mode_is_rejected():
    with pytest.raises(ValueError, match="invalid mode"):
        create_server(mode="invalid")


def test_read_only_mode_explicit():
    server = create_server(mode="ro")
    registered = set(server._tool_manager._tools)
    assert registered == set(READ_ONLY_TOOL_NAMES)


def test_folder_status_without_folder_uses_provider_statuses(tmp_path, monkeypatch):
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        '[accounts.personal]\nprovider = "gmail"\ncapabilities = ["mail"]\n'
    )
    state_file = tmp_path / "credentials.json"
    state_file.write_text("{}")
    core = Core(config_file=config_file, state_file=state_file)
    adapter = core._get_adapter("gmail")

    class Response:
        def json(self):
            return {
                "labels": [
                    {
                        "id": "INBOX",
                        "name": "INBOX",
                        "messagesTotal": 8,
                        "messagesUnread": 2,
                    }
                ]
            }

    monkeypatch.setattr(adapter, "_request", lambda *args, **kwargs: Response())
    monkeypatch.setattr(mcp, "get_core", lambda: core)

    assert mcp.mailhub_folder_status("personal", folder=None) == [
        {"folder": "INBOX", "messages": 8, "unseen": 2}
    ]
