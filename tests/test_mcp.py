"""Unit tests for mailhub.mcp module."""

from __future__ import annotations

import pytest

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


