"""stdio MCP surface for Mailhub (read-only and full modes)."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP as _FastMCP
from mcp.types import Resource, ResourceTemplate

from . import __version__


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


# --- Resource functions ---

def list_resources() -> list[Resource]:
    """List all available resources (folders for each account)."""
    c = _core_holder["core"]
    if c is None:
        return []
    
    resources = []
    for account in c.accounts_status():
        alias = account["alias"]
        try:
            folders = c.folders(alias)
            for folder in folders:
                resources.append(Resource(
                    uri=f"mailhub://{alias}/folders/{folder['name']}",
                    name=f"{alias}: {folder['name']}",
                    description=f"Folder {folder['name']} in account {alias}",
                    mimeType="application/json",
                ))
        except Exception:
            continue
    return resources


def read_resource(uri: str) -> str:
    """Read a resource by URI."""
    # Parse mailhub://{alias}/folders/{folder_name}
    if not uri.startswith("mailhub://"):
        raise ValueError(f"Unsupported URI scheme: {uri}")
    
    path = uri[len("mailhub://"):]
    parts = path.split("/")
    if len(parts) < 3 or parts[1] != "folders":
        raise ValueError(f"Invalid resource URI: {uri}")
    
    alias = parts[0]
    folder_name = "/".join(parts[2:])  # Handle nested folders
    
    c = get_core()
    try:
        # Get folder status
        status = c.folder_status(alias, folder_name)
        return json.dumps({
            "account": alias,
            "folder": folder_name,
            "status": status,
        }, indent=2)
    except Exception as e:
        raise ValueError(f"Failed to read resource: {e}")


def list_resource_templates() -> list[ResourceTemplate]:
    """List resource templates for dynamic resources."""
    return [
        ResourceTemplate(
            uriTemplate="mailhub://{account}/folders/{folder}",
            name="Mailhub Folder",
            description="Access a specific folder in an account",
            mimeType="application/json",
        ),
        ResourceTemplate(
            uriTemplate="mailhub://{account}/messages/{message_id}",
            name="Mailhub Message",
            description="Access a specific message by ID",
            mimeType="application/json",
        ),
        ResourceTemplate(
            uriTemplate="mailhub://{account}/search?q={query}",
            name="Mailhub Search",
            description="Search messages in an account",
            mimeType="application/json",
        ),
    ]


# --- Prompt functions ---

def compose_email_prompt(
    account: str,
    to: str,
    subject: str = "",
    cc: str = "",
    bcc: str = "",
    body: str = "",
    context: str = "",
) -> str:
    """Generate a draft email with the given parameters."""
    c = get_core()
    accounts = c.accounts_status()
    account_names = [a["alias"] for a in accounts]
    
    if account not in account_names:
        return f"Error: Account '{account}' not found. Available: {', '.join(account_names)}"
    
    prompt = f"""Compose an email:

**Account:** {account}
**To:** {to}
**CC:** {cc or '(none)'}
**BCC:** {bcc or '(none)'}
**Subject:** {subject or '(no subject)'}

**Context:** {context or 'New email'}

**Body:**
{body or '(write your message here)'}

Use the mailhub_draft tool to save this as a draft, or mailhub_send with confirm=true to send."""
    return prompt


def search_messages_prompt(
    account: str,
    query: str = "",
    folder: str = "INBOX",
    max_results: int = 20,
) -> str:
    """Guided search for messages."""
    c = get_core()
    accounts = c.accounts_status()
    account_names = [a["alias"] for a in accounts]
    
    if account not in account_names:
        return f"Error: Account '{account}' not found. Available: {', '.join(account_names)}"
    
    # Get available folders for context
    try:
        folders = c.folders(account)
        folder_names = [f["name"] for f in folders]
    except Exception:
        folder_names = []
    
    prompt = f"""Search messages in {account}:

**Folder:** {folder} (or specify another: {', '.join(folder_names[:10])}{'...' if len(folder_names) > 10 else ''})
**Query:** {query or '(empty = all messages)'}

**Search syntax:**
- `from:user@example.com` - Sender
- `to:user@example.com` - Recipient  
- `subject:text` - Subject line
- `body:text` - Message body (default)
- `before:YYYY-MM-DD` / `after:YYYY-MM-DD` - Date range
- `is:read` / `is:unread` - Read status
- `is:flagged` / `is:unflagged` - Flag status
- `has:attachment` - Has attachments
- `larger:N` / `smaller:N` - Size in bytes

**Max results:** {max_results}

Use mailhub_search to execute this search."""
    return prompt


def organize_inbox_prompt(
    account: str,
    rules: str = "",
) -> str:
    """Interactive inbox organization - move, archive, flag messages."""
    c = get_core()
    accounts = c.accounts_status()
    account_names = [a["alias"] for a in accounts]
    
    if account not in account_names:
        return f"Error: Account '{account}' not found. Available: {', '.join(account_names)}"
    
    try:
        folders = c.folders(account)
        folder_names = [f["name"] for f in folders]
        special = c.special_use_folders(account)
    except Exception:
        folder_names = []
        special = {}
    
    prompt = f"""Organize inbox for {account}:

**Special folders detected:**
- Inbox: {special.get('inbox', 'INBOX')}
- Archive: {special.get('archive', 'Archive')}
- Trash: {special.get('trash', 'Trash')}
- Spam/Junk: {special.get('junk', 'Junk')}

**Available folders:** {', '.join(folder_names[:15])}{'...' if len(folder_names) > 15 else ''}

**Rules / Actions:**
{rules or '(define your rules, e.g. "Move newsletters from from:newsletter@example.com to Archive", "Flag messages from boss@example.com")'}

**Available actions:**
- `mailhub_move` - Move single message
- `mailhub_batch_move` - Move multiple messages
- `mailhub_batch_delete` - Move multiple to Trash
- `mailhub_flag` / `mailhub_unflag` - Flag/unflag
- `mailhub_mark_read` / `mailhub_mark_unread` - Read status

Describe what you want to organize and I'll generate the tool calls."""
    return prompt


def check_unread_prompt(
    account: str,
) -> str:
    """Check unread message summary across folders."""
    c = get_core()
    accounts = c.accounts_status()
    account_names = [a["alias"] for a in accounts]
    
    if account not in account_names:
        return f"Error: Account '{account}' not found. Available: {', '.join(account_names)}"
    
    try:
        statuses = c.folder_statuses(account)
        special = c.special_use_folders(account)
    except Exception:
        statuses = []
        special = {}
    
    # Build summary
    total_unseen = 0
    summary_lines = []
    for s in statuses:
        folder = s.get("folder", "Unknown")
        messages = s.get("messages", 0)
        unseen = s.get("unseen", 0)
        total_unseen += unseen
        if unseen > 0:
            summary_lines.append(f"  {folder}: {messages} messages ({unseen} unread)")
    
    prompt = f"""Unread summary for {account}:

**Total unread:** {total_unseen}

**Folders with unread:**
{chr(10).join(summary_lines) if summary_lines else '  (none)'}

**Special folders:**
- Inbox: {special.get('inbox', 'INBOX')}
- Archive: {special.get('archive', 'Archive')}

**Quick actions:**
- Search unread: `mailhub_search(account="{account}", query="is:unread")`
- Mark all read: `mailhub_mark_read(account="{account}", message_ids=[...])`
- Move to archive: `mailhub_batch_move(account="{account}", message_ids=[...], destination="Archive")`"""
    return prompt


def create_draft_prompt(
    account: str,
    to: str,
    subject: str = "",
    cc: str = "",
    bcc: str = "",
    body: str = "",
    attachments: str = "",
) -> str:
    """Create a draft with optional attachments."""
    c = get_core()
    accounts = c.accounts_status()
    account_names = [a["alias"] for a in accounts]
    
    if account not in account_names:
        return f"Error: Account '{account}' not found. Available: {', '.join(account_names)}"
    
    prompt = f"""Create a draft in {account}:

**To:** {to}
**CC:** {cc or '(none)'}
**BCC:** {bcc or '(none)'}
**Subject:** {subject or '(no subject)'}

**Body:**
{body or '(write your message here)'}

**Attachments:** {attachments or '(none - specify file paths)'}

Use mailhub_draft to save, or mailhub_send with confirm=true to send immediately."""
    return prompt


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

    # Register resources
    @server.resource("mailhub://{account}/folders/{folder}")
    def mailhub_folder_resource(account: str, folder: str):
        """Access a specific folder in an account."""
        c = get_core()
        try:
            status = c.folder_status(account, folder)
            return json.dumps({
                "account": account,
                "folder": folder,
                "status": status,
            }, indent=2)
        except Exception as e:
            raise ValueError(f"Failed to read folder: {e}")

    @server.resource("mailhub://{account}/messages/{message_id}")
    def mailhub_message_resource(account: str, message_id: str):
        """Access a specific message by ID."""
        c = get_core()
        try:
            message = c.get(account, message_id)
            return json.dumps(message, indent=2)
        except Exception as e:
            raise ValueError(f"Failed to read message: {e}")

    @server.resource("mailhub://{account}/search?q={query}")
    def mailhub_search_resource(account: str, query: str):
        """Search messages in an account."""
        c = get_core()
        try:
            result = c.search(account, query, max_results=50)
            return json.dumps(result, indent=2)
        except Exception as e:
            raise ValueError(f"Failed to search: {e}")

    # Register prompts
    @server.prompt(name="compose_email", description="Compose a new email draft")
    def compose_email(account: str, to: str, subject: str = "", cc: str = "", bcc: str = "", body: str = "", context: str = "") -> str:
        return compose_email_prompt(account, to, subject, cc, bcc, body, context)

    @server.prompt(name="search_messages", description="Search messages with guided syntax")
    def search_messages(account: str, query: str = "", folder: str = "INBOX", max_results: int = 20) -> str:
        return search_messages_prompt(account, query, folder, max_results)

    @server.prompt(name="organize_inbox", description="Organize inbox with rules")
    def organize_inbox(account: str, rules: str = "") -> str:
        return organize_inbox_prompt(account, rules)

    @server.prompt(name="check_unread", description="Check unread message summary")
    def check_unread(account: str) -> str:
        return check_unread_prompt(account)

    @server.prompt(name="create_draft", description="Create a draft email")
    def create_draft(account: str, to: str, subject: str = "", cc: str = "", bcc: str = "", body: str = "", attachments: str = "") -> str:
        return create_draft_prompt(account, to, subject, cc, bcc, body, attachments)

    return server


def run_stdio(*, mode="ro", config_file=None):
    """Run the Mailhub MCP server over stdio."""
    create_server(mode=mode, config_file=config_file).run(transport="stdio")
