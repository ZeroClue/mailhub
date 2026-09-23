"""Thin REST client CLI for Mailhub (the `mail` command)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence
from urllib.parse import urlparse

import httpx

from .config import ConfigError, config_path, load_config
from .store import CredentialStore, state_path


DEFAULT_URL = "http://127.0.0.1:8787"
DEFAULT_TIMEOUT = 30.0


class MailCLIError(Exception):
    """Raised for mail CLI errors with exit code."""
    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


def _validate_loopback_url(url: str) -> str:
    """Validate that URL uses a loopback address (127.0.0.1 or localhost)."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise MailCLIError(f"URL must use loopback address (127.0.0.1/localhost), got: {host}")
    return url


def _resolve_paths(config_file: Path | None, state_file: Path | None) -> tuple[Path, Path]:
    """Resolve config and state file paths, using XDG defaults if not provided.
    
    If config_file is a file path, its parent directory is used as the base
    for the default state path.
    """
    # Resolve config path
    if config_file is not None:
        resolved_config = config_file
    else:
        resolved_config = config_path()
    
    # Resolve state path
    if state_file is not None:
        resolved_state = state_file
    else:
        # If config_file was explicitly provided as a file, use its parent as base
        if config_file is not None:
            base_dir = config_file.parent
        else:
            base_dir = None
        resolved_state = state_path(base_dir)
    
    return resolved_config, resolved_state


def _load_tokens(config_file: Path | None = None, state_file: Path | None = None) -> dict[str, str]:
    """Load ro_token and full_token from credential store."""
    _, resolved_state = _resolve_paths(config_file, state_file)
    store = CredentialStore(resolved_state)
    data = store.load()
    auth = data.get("auth", {})
    return {
        "ro_token": auth.get("ro_token", ""),
        "full_token": auth.get("full_token", ""),
    }


def _get_token(args: argparse.Namespace, config_file: Path | None, state_file: Path | None) -> str:
    """Determine which token to use based on flags."""
    tokens = _load_tokens(config_file, state_file)
    
    if args.token:
        return args.token
    if args.ro:
        token = tokens.get("ro_token")
        if not token:
            raise MailCLIError("No read-only token configured. Run 'mailhub serve' to generate tokens.")
        return token
    # Default to full token if neither specified
    token = tokens.get("full_token")
    if not token:
        raise MailCLIError("No full-access token configured. Run 'mailhub serve' to generate tokens.")
    return token


def _make_client(base_url: str, token: str) -> httpx.Client:
    """Create an httpx client with auth header and timeout."""
    headers = {"Authorization": f"Bearer {token}"}
    return httpx.Client(
        base_url=base_url,
        headers=headers,
        timeout=DEFAULT_TIMEOUT,
    )


def _handle_response(response: httpx.Response, expect_json: bool = True) -> dict | list | None:
    """Handle HTTP response, raise on error, return parsed JSON."""
    if response.status_code == 401:
        raise MailCLIError("Authentication failed (401): token may be expired or invalid", 1)
    if response.status_code == 403:
        detail = ""
        try:
            detail = f": {response.json().get('error', '')}"
        except Exception:
            detail = f": {response.text[:200]}"
        raise MailCLIError(f"Access denied (403){detail}", 1)
    if response.status_code >= 500:
        raise MailCLIError(f"Server error ({response.status_code}): {response.text[:200]}", 1)
    if response.status_code >= 400:
        detail = ""
        try:
            detail = f": {response.json().get('error', '')}"
        except Exception:
            detail = f": {response.text[:200]}"
        raise MailCLIError(f"Request failed ({response.status_code}){detail}", 1)
    
    if not expect_json:
        return None
    
    try:
        return response.json()
    except Exception:
        return None


def _output(data: object, as_json: bool) -> None:
    """Output data as JSON or formatted text."""
    if as_json:
        json.dump(data, sys.stdout, indent=2, ensure_ascii=False)
        print()
    else:
        # Pretty print for non-JSON output
        if isinstance(data, dict):
            for key, value in data.items():
                print(f"{key}: {value}")
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    for k, v in item.items():
                        print(f"  {k}: {v}")
                    print()
                else:
                    print(f"  {item}")
        else:
            print(data)


def cmd_accounts(args: argparse.Namespace, config_file: Path | None, state_file: Path | None) -> int:
    """List configured accounts."""
    token = _get_token(args, config_file, state_file)
    client = _make_client(args.url, token)
    
    try:
        response = client.get("/accounts")
        data = _handle_response(response)
        _output(data, args.json)
        return 0
    finally:
        client.close()


def cmd_folders(args: argparse.Namespace, config_file: Path | None, state_file: Path | None) -> int:
    """List folders/labels for an account."""
    token = _get_token(args, config_file, state_file)
    client = _make_client(args.url, token)
    
    try:
        response = client.get(f"/accounts/{args.account}/folders")
        data = _handle_response(response)
        # API returns {"folders": [...]}
        folders = data.get("folders", []) if isinstance(data, dict) else data
        _output(folders, args.json)
        return 0
    finally:
        client.close()


def cmd_search(args: argparse.Namespace, config_file: Path | None, state_file: Path | None) -> int:
    """Search messages."""
    token = _get_token(args, config_file, state_file)
    client = _make_client(args.url, token)
    
    try:
        params = {"q": args.query, "max_results": args.max_results}
        if args.page_token:
            params["page_token"] = args.page_token
        response = client.get(f"/accounts/{args.account}/messages", params=params)
        data = _handle_response(response)
        _output(data, args.json)
        return 0
    finally:
        client.close()


def cmd_get(args: argparse.Namespace, config_file: Path | None, state_file: Path | None) -> int:
    """Get message by ID."""
    token = _get_token(args, config_file, state_file)
    client = _make_client(args.url, token)
    
    try:
        response = client.get(f"/accounts/{args.account}/messages/{args.message_id}")
        data = _handle_response(response)
        _output(data, args.json)
        return 0
    finally:
        client.close()


def cmd_send(args: argparse.Namespace, config_file: Path | None, state_file: Path | None) -> int:
    """Send a message (requires --confirm)."""
    if not args.confirm:
        raise MailCLIError("Sending requires --confirm flag", 1)
    
    token = _get_token(args, config_file, state_file)
    # Must use full token for send
    tokens = _load_tokens(config_file, state_file)
    if token != tokens.get("full_token") and not args.token:
        raise MailCLIError("Send operation requires full-access token (use --token with full token)", 1)
    
    client = _make_client(args.url, token)
    
    try:
        # Read message from stdin if not provided
        text_body = args.text_body
        html_body = args.html_body
        if args.body_file:
            with open(args.body_file, "r") as f:
                content = f.read()
            if args.html:
                html_body = content
            else:
                text_body = content
        elif not text_body and not html_body and not sys.stdin.isatty():
            # Read from stdin
            content = sys.stdin.read()
            if args.html:
                html_body = content
            else:
                text_body = content
        
        payload = {
            "to": args.to,
            "cc": args.cc or [],
            "bcc": args.bcc or [],
            "subject": args.subject,
            "text_body": text_body,
            "html_body": html_body,
            "in_reply_to": args.in_reply_to,
            "references": args.references or [],
            "confirm": True,
        }
        response = client.post(f"/accounts/{args.account}/send", json=payload)
        data = _handle_response(response)
        _output(data, args.json)
        return 0
    finally:
        client.close()


def cmd_draft(args: argparse.Namespace, config_file: Path | None, state_file: Path | None) -> int:
    """Create a draft."""
    token = _get_token(args, config_file, state_file)
    # Must use full token for draft
    tokens = _load_tokens(config_file, state_file)
    if token != tokens.get("full_token") and not args.token:
        raise MailCLIError("Draft operation requires full-access token (use --token with full token)", 1)
    
    client = _make_client(args.url, token)
    
    try:
        # Read message from stdin if not provided
        text_body = args.text_body
        html_body = args.html_body
        if args.body_file:
            with open(args.body_file, "r") as f:
                content = f.read()
            if args.html:
                html_body = content
            else:
                text_body = content
        elif not text_body and not html_body and not sys.stdin.isatty():
            # Read from stdin
            content = sys.stdin.read()
            if args.html:
                html_body = content
            else:
                text_body = content
        
        payload = {
            "to": args.to,
            "cc": args.cc or [],
            "bcc": args.bcc or [],
            "subject": args.subject,
            "text_body": text_body,
            "html_body": html_body,
            "in_reply_to": args.in_reply_to,
            "references": args.references or [],
        }
        response = client.post(f"/accounts/{args.account}/draft", json=payload)
        data = _handle_response(response)
        _output(data, args.json)
        return 0
    finally:
        client.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mail",
        description="Thin REST client for Mailhub API",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help=f"Mailhub REST API base URL (default: {DEFAULT_URL})",
    )
    parser.add_argument(
        "--token",
        help="Bearer token to use (overrides --ro and config)",
    )
    parser.add_argument(
        "--ro",
        action="store_true",
        help="Use read-only token from config",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Configuration file path",
    )
    parser.add_argument(
        "--state",
        type=Path,
        help="Credential state file path",
    )
    
    subcommands = parser.add_subparsers(dest="command", required=True)
    
    # accounts
    subcommands.add_parser("accounts", help="List configured accounts")
    
    # folders
    folders = subcommands.add_parser("folders", help="List folders/labels for an account")
    folders.add_argument("account", help="Account alias")
    
    # search
    search = subcommands.add_parser("search", help="Search messages")
    search.add_argument("account", help="Account alias")
    search.add_argument("query", help="Search query")
    search.add_argument("--max-results", type=int, default=50, help="Maximum results (default: 50)")
    search.add_argument("--page-token", help="Page token for pagination")
    
    # get
    get = subcommands.add_parser("get", help="Get message by ID")
    get.add_argument("account", help="Account alias")
    get.add_argument("message_id", help="Message ID")
    
    # send
    send = subcommands.add_parser("send", help="Send a message (requires --confirm)")
    send.add_argument("account", help="Account alias")
    send.add_argument("--to", action="append", required=True, help="Recipient email (repeatable)")
    send.add_argument("--cc", action="append", help="CC recipient (repeatable)")
    send.add_argument("--bcc", action="append", help="BCC recipient (repeatable)")
    send.add_argument("--subject", required=True, help="Message subject")
    send.add_argument("--text-body", help="Plain text body")
    send.add_argument("--html-body", help="HTML body")
    send.add_argument("--html", action="store_true", help="Treat body as HTML (for stdin/file)")
    send.add_argument("--body-file", help="Read body from file")
    send.add_argument("--in-reply-to", help="In-Reply-To header")
    send.add_argument("--references", action="append", help="References header (repeatable)")
    send.add_argument("--confirm", action="store_true", required=True, help="Confirm sending (required)")
    
    # draft
    draft = subcommands.add_parser("draft", help="Create a draft")
    draft.add_argument("account", help="Account alias")
    draft.add_argument("--to", action="append", required=True, help="Recipient email (repeatable)")
    draft.add_argument("--cc", action="append", help="CC recipient (repeatable)")
    draft.add_argument("--bcc", action="append", help="BCC recipient (repeatable)")
    draft.add_argument("--subject", required=True, help="Message subject")
    draft.add_argument("--text-body", help="Plain text body")
    draft.add_argument("--html-body", help="HTML body")
    draft.add_argument("--html", action="store_true", help="Treat body as HTML (for stdin/file)")
    draft.add_argument("--body-file", help="Read body from file")
    draft.add_argument("--in-reply-to", help="In-Reply-To header")
    draft.add_argument("--references", action="append", help="References header (repeatable)")
    
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    
    # Validate URL early
    try:
        args.url = _validate_loopback_url(args.url)
    except MailCLIError as e:
        print(f"mail: {e}", file=sys.stderr)
        return e.exit_code
    
    # Resolve config and state paths
    resolved_config, resolved_state = _resolve_paths(args.config, args.state)
    
    # Check config exists
    if not resolved_config.exists():
        print(f"mail: configuration not found: {resolved_config}; run 'mailhub init'", file=sys.stderr)
        return 2
    
    try:
        load_config(resolved_config)
    except ConfigError as e:
        print(f"mail: {e}", file=sys.stderr)
        return 2
    
    # Route to command
    try:
        if args.command == "accounts":
            return cmd_accounts(args, args.config, args.state)
        elif args.command == "folders":
            return cmd_folders(args, args.config, args.state)
        elif args.command == "search":
            return cmd_search(args, args.config, args.state)
        elif args.command == "get":
            return cmd_get(args, args.config, args.state)
        elif args.command == "send":
            return cmd_send(args, args.config, args.state)
        elif args.command == "draft":
            return cmd_draft(args, args.config, args.state)
    except MailCLIError as e:
        print(f"mail: {e}", file=sys.stderr)
        return e.exit_code
    except httpx.ConnectError:
        print(f"mail: cannot connect to {args.url}; is 'mailhub serve' running?", file=sys.stderr)
        return 1
    except httpx.TimeoutException:
        print(f"mail: request timed out", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"mail: unexpected error: {e}", file=sys.stderr)
        return 1
    
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
