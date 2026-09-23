"""Core policy engine: account registry, credentials, policy, retries, audit."""

from __future__ import annotations

import json
import os
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal

import httpx

from .config import Account, Config, ConfigError, load_config
from .oauth import Provider, ReauthNeeded, refresh
from .store import CredentialStore, StoreError
from .util import split_addrs

__all__ = ["Core", "CoreError", "SendDenied", "AuditEntry"]


class CoreError(ValueError):
    """Raised for core policy/credential errors."""


class SendDenied(CoreError):
    """Raised when a send is denied by policy (allowlist/confirm)."""


@dataclass(frozen=True)
class AuditEntry:
    """An audit log entry for mutating operations."""
    timestamp: str
    account: str
    operation: str
    details: dict[str, object]


@dataclass
class RetryPolicy:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0


@dataclass
class SendPolicy:
    """Send policy configuration."""
    allowlist: tuple[str, ...] = ()
    allow_anywhere: bool = False


@dataclass
class AccountCredentials:
    """Stored credentials for an account."""
    access_token: str | None = None
    refresh_token: str | None = None
    expires_at: float | None = None  # Unix timestamp
    client_id: str | None = None
    client_secret: str | None = None


# Fields that should never be logged in audit
_SENSITIVE_FIELDS = {
    "access_token", "refresh_token", "client_secret", "password",
    "authorization", "bearer", "token", "secret", "code_verifier"
}


def _sanitize_for_audit(details: dict[str, object]) -> dict[str, object]:
    """Remove sensitive fields from audit details."""
    if not isinstance(details, dict):
        return {}
    sanitized = {}
    for k, v in details.items():
        if k.lower() in _SENSITIVE_FIELDS:
            sanitized[k] = "[REDACTED]"
        elif isinstance(v, dict):
            sanitized[k] = _sanitize_for_audit(v)
        else:
            sanitized[k] = v
    return sanitized


def _state_path(config_file: Path | None = None) -> Path:
    """Get the default state path based on config file or XDG."""
    if config_file is not None:
        return config_file.parent / "mailhub" / "credentials.json"
    root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return root / "mailhub" / "credentials.json"


class Core:
    """
    Core policy engine managing accounts, credentials, policy, retries, and audit.

    Lazy-loads provider adapters (gmail, graph) on first use.
    """

    def __init__(
        self,
        config: Config | None = None,
        config_file: Path | None = None,
        state_file: Path | None = None,
        audit_file: Path | None = None,
        retry_policy: RetryPolicy | None = None,
        send_policy: SendPolicy | None = None,
    ) -> None:
        self._config = config or load_config(config_file)
        self._store = CredentialStore(state_file)
        self._audit_path = audit_file or _state_path(config_file).parent / "audit.jsonl"
        self._retry_policy = retry_policy or RetryPolicy()
        self._send_policy = send_policy or SendPolicy()
        self._adapters: dict[str, Any] = {}
        self._credentials_cache: dict[str, AccountCredentials] = {}

    def _load_credentials(self, alias: str) -> AccountCredentials:
        """Load credentials for an account from the store."""
        if alias in self._credentials_cache:
            return self._credentials_cache[alias]

        data = self._store.load()
        account_data = data.get("accounts", {}).get(alias, {})
        creds = AccountCredentials(
            access_token=account_data.get("access_token"),
            refresh_token=account_data.get("refresh_token"),
            expires_at=account_data.get("expires_at"),
            client_id=account_data.get("client_id"),
            client_secret=account_data.get("client_secret"),
        )
        self._credentials_cache[alias] = creds
        return creds

    def _save_credentials(self, alias: str, creds: AccountCredentials) -> None:
        """Save credentials for an account to the store."""
        data = self._store.load()
        accounts = data.setdefault("accounts", {})
        accounts[alias] = {
            "access_token": creds.access_token,
            "refresh_token": creds.refresh_token,
            "expires_at": creds.expires_at,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
        }
        self._store.save(data)
        self._credentials_cache[alias] = creds

    def _get_adapter(self, provider: str) -> Any:
        """Lazy-load and return a provider adapter."""
        if provider not in self._adapters:
            if provider == "gmail":
                from .gmail import GmailAdapter
                self._adapters[provider] = GmailAdapter(self)
            elif provider == "graph":
                from .graph import GraphAdapter
                self._adapters[provider] = GraphAdapter(self)
            else:
                raise CoreError(f"unsupported provider: {provider}")
        return self._adapters[provider]

    def _ensure_access_token(self, alias: str) -> str:
        """Get a valid access token, refreshing if necessary."""
        account = self._config.account(alias)
        creds = self._load_credentials(alias)

        if creds.access_token and creds.expires_at and time.time() < creds.expires_at - 60:
            return creds.access_token

        if not creds.refresh_token:
            raise CoreError(f"no refresh token for account {alias}; run auth flow")

        if not creds.client_id or not creds.client_secret:
            raise CoreError(f"missing client credentials for account {alias}")

        provider: Provider = account.provider  # type: ignore[assignment]
        try:
            token_resp = refresh(provider, creds.client_id, creds.client_secret, creds.refresh_token)
        except ReauthNeeded:
            raise CoreError(f"refresh token expired for {alias}; re-authenticate")

        creds.access_token = token_resp.get("access_token")
        if "refresh_token" in token_resp:
            creds.refresh_token = token_resp["refresh_token"]
        expires_in = token_resp.get("expires_in", 3600)
        creds.expires_at = time.time() + expires_in
        self._save_credentials(alias, creds)
        return creds.access_token

    def _refresh_access_token(self, alias: str) -> str:
        """Refresh the access token using the refresh token (public wrapper)."""
        return self._ensure_access_token(alias)

    def _audit(self, account: str, operation: str, details: dict[str, object]) -> None:
        """Write an audit log entry (never includes tokens or bodies)."""
        self._audit_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "account": account,
            "operation": operation,
            "details": _sanitize_for_audit(details),
        }
        with self._audit_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def accounts_status(self) -> list[dict[str, object]]:
        """Return status for all configured accounts."""
        out = []
        for account in self._config.accounts:
            creds = self._load_credentials(account.alias)
            out.append({
                "alias": account.alias,
                "provider": account.provider,
                "email": account.email,
                "has_refresh_token": creds.refresh_token is not None,
                "has_access_token": creds.access_token is not None,
            })
        return out

    def doctor(self) -> list[dict[str, object]]:
        """Check health of all accounts."""
        out = []
        for account in self._config.accounts:
            try:
                adapter = self._get_adapter(account.provider)
                profile = adapter.profile(account.alias)
                out.append({"alias": account.alias, "provider": account.provider, "status": "ok", "profile": profile})
            except ReauthNeeded:
                out.append({"alias": account.alias, "provider": account.provider, "status": "needs_reauth"})
            except Exception as e:
                out.append({"alias": account.alias, "provider": account.provider, "status": "error", "detail": str(e)[:200]})
        return out

    def search(
        self,
        account: str,
        query: str,
        *,
        max_results: int = 50,
        page_token: str | None = None,
    ) -> dict[str, object]:
        """Search messages in an account."""
        adapter = self._get_adapter(self._config.account(account).provider)
        return adapter.search(account, query, max_results=max_results, page_token=page_token)

    def get(self, account: str, message_id: str) -> dict[str, object]:
        """Get a message by ID."""
        adapter = self._get_adapter(self._config.account(account).provider)
        return adapter.get(account, message_id)

    def send(
        self,
        account: str,
        *,
        to: list[str],
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        subject: str,
        text_body: str | None = None,
        html_body: str | None = None,
        in_reply_to: str | None = None,
        references: list[str] | None = None,
        confirm: bool = False,
    ) -> dict[str, object]:
        """Send a message (requires confirm=true and allowlist check)."""
        # Check confirm first (fail fast)
        if not confirm:
            raise SendDenied("send requires confirm=true")

        # Check allowlist
        all_recipients = set(to)
        if cc:
            all_recipients.update(cc)
        if bcc:
            all_recipients.update(bcc)

        if not self._send_policy.allow_anywhere:
            allowed = False
            for pattern in self._send_policy.allowlist:
                for recipient in all_recipients:
                    if _match_glob(pattern, recipient):
                        allowed = True
                        break
                if allowed:
                    break
            if not allowed:
                self._audit(account, "send_blocked", {"recipients": list(all_recipients)})
                raise SendDenied("recipient not in allowlist")

        adapter = self._get_adapter(self._config.account(account).provider)
        result = adapter.send(
            account,
            to=to,
            cc=cc or [],
            bcc=bcc or [],
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            in_reply_to=in_reply_to,
            references=references or [],
        )
        self._audit(account, "send", {
            "to": to,
            "cc": cc or [],
            "subject": subject,
            "message_id": result.get("id"),
        })
        return result

    def draft(
        self,
        account: str,
        *,
        to: list[str],
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        subject: str,
        text_body: str | None = None,
        html_body: str | None = None,
        in_reply_to: str | None = None,
        references: list[str] | None = None,
    ) -> dict[str, object]:
        """Create a draft message."""
        adapter = self._get_adapter(self._config.account(account).provider)
        result = adapter.draft(
            account,
            to=to,
            cc=cc or [],
            bcc=bcc or [],
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            in_reply_to=in_reply_to,
            references=references or [],
        )
        self._audit(account, "draft", {
            "to": to,
            "cc": cc or [],
            "subject": subject,
            "draft_id": result.get("id"),
        })
        return result

    def move(self, account: str, message_id: str, destination: str) -> dict[str, object]:
        """Move a message to a folder/label."""
        adapter = self._get_adapter(self._config.account(account).provider)
        result = adapter.move(account, message_id, destination)
        self._audit(account, "move", {
            "message_id": message_id,
            "destination": destination,
            "new_id": result.get("id"),
        })
        return result

    def trash(self, account: str, message_id: str) -> dict[str, object]:
        """Move a message to trash (no hard delete)."""
        adapter = self._get_adapter(self._config.account(account).provider)
        result = adapter.trash(account, message_id)
        self._audit(account, "trash", {"message_id": message_id})
        return result

    def folders(self, account: str) -> list[dict[str, object]]:
        """List folders/labels for an account."""
        adapter = self._get_adapter(self._config.account(account).provider)
        return adapter.folders(account)


def _match_glob(pattern: str, value: str) -> bool:
    """Match a value against a glob pattern (supports * and ?), case-insensitive."""
    regex = re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".")
    return re.fullmatch(regex, value, re.IGNORECASE) is not None


