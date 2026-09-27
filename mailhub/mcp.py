"""stdio MCP surface for Mailhub (read-only and full modes)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP as _FastMCP

from . import __version__
from .config import ConfigError, load_config
from .core import Core, CoreError, SendDenied


READ_ONLY_TOOL_NAMES = ("mailhub_status",)
FULL_TOOL_NAMES = (
    "mailhub_status",
    "mailhub_search",
    "mailhub_get",
    "mailhub_send",
    "mailhub_draft",
    "mailhub_move",
    "mailhub_trash",
    "mailhub_folders",
    "mailhub_folder_status",
    "mailhub_special_folders",
    "mailhub_create_folder",
    "mailhub_delete_folder",
    "mailhub_rename_folder",
    "mailhub_mark_read",
    "mailhub_mark_unread",
    "mailhub_flag",
    "mailhub_unflag",
    "mailhub_batch_move",
    "mailhub_batch_delete",
)

# Module-level core holder
_core_holder = {"core": None}


def _set_core(core):
    _core_holder["core"] = core


def get_core():
    c = _core_holder["core"]
    if c is None:
        from .core import CoreError
        raise CoreError("mailhub not configured; run 'mailhub init'")
    return c


# Tool functions defined at module level to avoid closure issues
def mailhub_status():
    """Return non-secret account configuration; never contact a provider."""
    c = _core_holder["core"]
    if c is None:
        return {"configured": False, "error": "not configured", "accounts": []}
    return {"configured": True, "accounts": c.accounts_status()}


def mailhub_search(account, query, max_results=50, page_token=None):
    c = get_core()
    return c.search(account, query, max_results=max_results, page_token=page_token)


def mailhub_get(account, message_id):
    c = get_core()
    return c.get(account, message_id)


def mailhub_send(
    account,
    to,
    subject,
    cc=None,
    bcc=None,
    text_body=None,
    html_body=None,
    in_reply_to=None,
    references=None,
    confirm=False,
    attachments=None,
):
    c = get_core()
    if not confirm:
        from .core import SendDenied
        raise SendDenied("send requires confirm=true")
    return c.send(
        account,
        to=to,
        cc=cc or [],
        bcc=bcc or [],
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        in_reply_to=in_reply_to,
        references=references or [],
        confirm=True,
        attachments=attachments or [],
    )


def mailhub_draft(
    account,
    to,
    subject,
    cc=None,
    bcc=None,
    text_body=None,
    html_body=None,
    in_reply_to=None,
    references=None,
    attachments=None,
):
    c = get_core()
    return c.draft(
        account,
        to=to,
        cc=cc or [],
        bcc=bcc or [],
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        in_reply_to=in_reply_to,
        references=references or [],
        attachments=attachments or [],
    )


def mailhub_move(account, message_id, destination):
    c = get_core()
    return c.move(account, message_id, destination)


def mailhub_trash(account, message_id):
    c = get_core()
    return c.trash(account, message_id)


def mailhub_folders(account):
    c = get_core()
    return c.folders(account)


def mailhub_folder_status(account, folder=None):
    c = get_core()
    if folder:
        return c.folder_status(account, folder)
    return c.folder_statuses(account)


def mailhub_special_folders(account):
    c = get_core()
    return c.special_use_folders(account)


def mailhub_create_folder(account, name):
    c = get_core()
    return c.create_folder(account, name)


def mailhub_delete_folder(account, name):
    c = get_core()
    return c.delete_folder(account, name)


def mailhub_rename_folder(account, old_name, new_name):
    c = get_core()
    return c.rename_folder(account, old_name, new_name)


def mailhub_mark_read(account, message_ids):
    c = get_core()
    return c.mark_read(account, message_ids)


def mailhub_mark_unread(account, message_ids):
    c = get_core()
    return c.mark_unread(account, message_ids)


def mailhub_flag(account, message_ids):
    c = get_core()
    return c.flag_messages(account, message_ids)


def mailhub_unflag(account, message_ids):
    c = get_core()
    return c.unflag_messages(account, message_ids)


def mailhub_batch_move(account, message_ids, destination):
    c = get_core()
    return c.batch_move(account, message_ids, destination)


def mailhub_batch_delete(account, message_ids):
    c = get_core()
    return c.batch_delete(account, message_ids)


def create_server(*, mode="ro", config_file=None):
    """Create an MCP server with specified mode."""
    if mode not in ("ro", "full"):
        raise ValueError(f"invalid mode: {mode}; must be 'ro' or 'full'")

    # Load core
    try:
        from .core import Core
        from .config import load_config
        core = Core(config=load_config(config_file))
    except Exception:
        core = None

    _core_holder["core"] = core

    from mcp.server.fastmcp import FastMCP
    # Create server with name, version, and instructions for proper initialize response
    server = _FastMCP(
        name="mailhub",
        instructions=(
            "Mailhub - Local personal-operations hub for mail, calendar, contacts, and tasks. "
            "Supports Gmail, Microsoft Graph, IMAP/SMTP, CalDAV, and CardDAV. "
            "Use --mode ro for read-only access, --mode full for mutations."
        ),
    )
    # Set version on underlying MCP server for initialize response
    server._mcp_server.version = __version__

    @server.tool(name="mailhub_status", description="List configured Mailhub accounts and capabilities.")
    def mailhub_status_tool():
        """Return non-secret account configuration; never contact a provider."""
        c = _core_holder["core"]
        if c is None:
            return {"configured": False, "error": "not configured", "accounts": []}
        return {"configured": True, "accounts": c.accounts_status()}

    if mode == "full":
        # Register mutation tools
        @server.tool(name="mailhub_search", description="Search messages in an account.")
        def mailhub_search_tool(account, query, max_results=50, page_token=None):
            c = get_core()
            return c.search(account, query, max_results=max_results, page_token=page_token)

        @server.tool(name="mailhub_get", description="Get a message by ID.")
        def mailhub_get_tool(account, message_id):
            c = get_core()
            return c.get(account, message_id)

        @server.tool(name="mailhub_send", description="Send a message (requires confirm=true).")
        def mailhub_send_tool(
            account,
            to,
            subject,
            cc=None,
            bcc=None,
            text_body=None,
            html_body=None,
            in_reply_to=None,
            references=None,
            confirm=False,
            attachments=None,
        ):
            c = get_core()
            if not confirm:
                from .core import SendDenied
                raise SendDenied("send requires confirm=true")
            return c.send(
                account,
                to=to,
                cc=cc or [],
                bcc=bcc or [],
                subject=subject,
                text_body=text_body,
                html_body=html_body,
                in_reply_to=in_reply_to,
                references=references or [],
                confirm=True,
                attachments=attachments or [],
            )

        @server.tool(name="mailhub_draft", description="Create a draft message.")
        def mailhub_draft_tool(
            account,
            to,
            subject,
            cc=None,
            bcc=None,
            text_body=None,
            html_body=None,
            in_reply_to=None,
            references=None,
            attachments=None,
        ):
            c = get_core()
            return c.draft(
                account,
                to=to,
                cc=cc or [],
                bcc=bcc or [],
                subject=subject,
                text_body=text_body,
                html_body=html_body,
                in_reply_to=in_reply_to,
                references=references or [],
                attachments=attachments or [],
            )

        @server.tool(name="mailhub_move", description="Move a message to a folder/label.")
        def mailhub_move_tool(account, message_id, destination):
            c = get_core()
            return c.move(account, message_id, destination)

        @server.tool(name="mailhub_trash", description="Move a message to trash.")
        def mailhub_trash_tool(account, message_id):
            c = get_core()
            return c.trash(account, message_id)

        @server.tool(name="mailhub_folders", description="List folders/labels for an account.")
        def mailhub_folders_tool(account):
            c = get_core()
            return c.folders(account)

        @server.tool(name="mailhub_folder_status", description="Get folder status (message counts, unseen) for an account or specific folder.")
        def mailhub_folder_status_tool(account, folder=None):
            c = get_core()
            if folder:
                return c.folder_status(account, folder)
            return c.folder_statuses(account)

        @server.tool(name="mailhub_special_folders", description="Detect special-use folders (Inbox, Sent, Drafts, Trash, Junk, Archive).")
        def mailhub_special_folders_tool(account):
            c = get_core()
            return c.special_use_folders(account)

        @server.tool(name="mailhub_create_folder", description="Create a new IMAP folder.")
        def mailhub_create_folder_tool(account, name):
            c = get_core()
            return c.create_folder(account, name)

        @server.tool(name="mailhub_delete_folder", description="Delete an IMAP folder.")
        def mailhub_delete_folder_tool(account, name):
            c = get_core()
            return c.delete_folder(account, name)

        @server.tool(name="mailhub_rename_folder", description="Rename an IMAP folder.")
        def mailhub_rename_folder_tool(account, old_name, new_name):
            c = get_core()
            return c.rename_folder(account, old_name, new_name)

        @server.tool(name="mailhub_mark_read", description="Mark messages as read (add \\Seen flag).")
        def mailhub_mark_read_tool(account, message_ids):
            c = get_core()
            return c.mark_read(account, message_ids)

        @server.tool(name="mailhub_mark_unread", description="Mark messages as unread (remove \\Seen flag).")
        def mailhub_mark_unread_tool(account, message_ids):
            c = get_core()
            return c.mark_unread(account, message_ids)

        @server.tool(name="mailhub_flag", description="Flag messages (add \\Flagged flag).")
        def mailhub_flag_tool(account, message_ids):
            c = get_core()
            return c.flag_messages(account, message_ids)

        @server.tool(name="mailhub_unflag", description="Unflag messages (remove \\Flagged flag).")
        def mailhub_unflag_tool(account, message_ids):
            c = get_core()
            return c.unflag_messages(account, message_ids)

        @server.tool(name="mailhub_batch_move", description="Move multiple messages to a folder.")
        def mailhub_batch_move_tool(account, message_ids, destination):
            c = get_core()
            return c.batch_move(account, message_ids, destination)

        @server.tool(name="mailhub_batch_delete", description="Move multiple messages to Trash.")
        def mailhub_batch_delete_tool(account, message_ids):
            c = get_core()
            return c.batch_delete(account, message_ids)

    return server


def run_stdio(*, mode="ro", config_file=None):
    """Run the Mailhub MCP server over stdio."""
    create_server(mode=mode, config_file=config_file).run(transport="stdio")
