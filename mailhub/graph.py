"""Microsoft Graph API adapter - full implementation for M2."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

import httpx

from .core import Core
from .util import build_mime

# Graph API base URL
GRAPH_BASE = "https://graph.microsoft.com/v1.0/me"


@dataclass
class _Attachment:
    """Internal representation of an attachment."""
    attachment_id: str
    filename: str
    mime_type: str
    size: int


class GraphAdapter:
    """Microsoft Graph API adapter (synchronous)."""

    def __init__(self, core: Core) -> None:
        self._core = core
        self._client: httpx.Client | None = None
        self._folders_cache: dict[str, list[dict[str, object]]] = {}

    def _get_client(self) -> httpx.Client:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.Client(timeout=30.0)
        return self._client

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def _auth_header(self, alias: str) -> dict[str, str]:
        """Build Authorization header with access token."""
        token = self._core._ensure_access_token(alias)
        return {"Authorization": f"Bearer {token}"}

    def _request(
        self,
        method: str,
        url: str,
        alias: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Make an authenticated request with retry logic."""
        client = self._get_client()
        request_headers = self._auth_header(alias)
        if headers:
            request_headers.update(headers)

        retry_policy = self._core._retry_policy

        for attempt in range(retry_policy.max_attempts):
            try:
                response = client.request(
                    method,
                    url,
                    params=params,
                    json=json_data,
                    headers=request_headers,
                )

                # Handle 401 - force token refresh and retry once
                if response.status_code == 401:
                    if attempt == 0:  # Only retry once on 401
                        self._core._refresh_access_token(alias)
                        request_headers = self._auth_header(alias)
                        if headers:
                            request_headers.update(headers)
                        continue
                    response.raise_for_status()

                # Handle 429 and 5xx - retry with backoff
                if response.status_code == 429 or 500 <= response.status_code < 600:
                    if attempt < retry_policy.max_attempts - 1:
                        retry_after = response.headers.get("Retry-After")
                        if retry_after:
                            try:
                                delay = float(retry_after)
                            except ValueError:
                                delay = retry_policy.base_delay * (2 ** attempt)
                        else:
                            delay = retry_policy.base_delay * (2 ** attempt)
                        delay = min(delay, retry_policy.max_delay)
                        import time
                        time.sleep(delay)
                        continue
                    response.raise_for_status()

                response.raise_for_status()
                return response

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401 and attempt == 0:
                    self._core._refresh_access_token(alias)
                    request_headers = self._auth_header(alias)
                    if headers:
                        request_headers.update(headers)
                    continue
                if e.response.status_code in (429,) or 500 <= e.response.status_code < 600:
                    if attempt < retry_policy.max_attempts - 1:
                        retry_after = e.response.headers.get("Retry-After")
                        if retry_after:
                            try:
                                delay = float(retry_after)
                            except ValueError:
                                delay = retry_policy.base_delay * (2 ** attempt)
                        else:
                            delay = retry_policy.base_delay * (2 ** attempt)
                        delay = min(delay, retry_policy.max_delay)
                        import time
                        time.sleep(delay)
                        continue
                raise

            except httpx.RequestError as e:
                if attempt < retry_policy.max_attempts - 1:
                    delay = retry_policy.base_delay * (2 ** attempt)
                    delay = min(delay, retry_policy.max_delay)
                    import time
                    time.sleep(delay)
                    continue
                raise

        raise RuntimeError("unreachable")

    def profile(self, alias: str) -> dict[str, object]:
        """Get user profile."""
        response = self._request("GET", f"{GRAPH_BASE}/profile", alias)
        data = response.json()
        return {
            "email": data.get("mail") or data.get("userPrincipalName"),
            "provider": "graph",
            "display_name": data.get("displayName"),
            "id": data.get("id"),
        }

    def folders(self, alias: str) -> list[dict[str, object]]:
        """List mail folders (with caching)."""
        if alias in self._folders_cache:
            return self._folders_cache[alias]
        
        response = self._request("GET", f"{GRAPH_BASE}/mailFolders", alias)
        data = response.json()
        folders = []
        for folder in data.get("value", []):
            folders.append({
                "id": folder["id"],
                "name": folder["displayName"],
                "type": "folder",
                "child_folder_count": folder.get("childFolderCount"),
                "total_item_count": folder.get("totalItemCount"),
                "unread_item_count": folder.get("unreadItemCount"),
            })
        self._folders_cache[alias] = folders
        return folders

    def search(
        self,
        alias: str,
        query: str,
        *,
        max_results: int = 50,
        page_token: str | None = None,
    ) -> dict[str, object]:
        """Search messages using Graph $filter or $search."""
        params = {"$top": max_results}
        if query:
            # Use $search for full-text search
            params["$search"] = f'"{query}"'
        if page_token:
            params["$skiptoken"] = page_token

        response = self._request("GET", f"{GRAPH_BASE}/messages", alias, params=params)
        data = response.json()

        messages = []
        for msg in data.get("value", []):
            messages.append(self._parse_message(msg))

        return {
            "messages": messages,
            "next_page_token": data.get("@odata.nextLink", "").split("$skiptoken=")[-1] if "@odata.nextLink" in data else None,
        }

    def _parse_message(self, data: dict) -> dict[str, object]:
        """Parse Graph message format."""
        from_addr = data.get("from", {}).get("emailAddress", {})
        to_addrs = data.get("toRecipients", [])
        cc_addrs = data.get("ccRecipients", [])

        return {
            "id": data.get("id"),
            "conversation_id": data.get("conversationId"),
            "from": {"name": from_addr.get("name"), "addr": from_addr.get("address")},
            "to": [{"name": r.get("emailAddress", {}).get("name"), "addr": r.get("emailAddress", {}).get("address")} for r in to_addrs],
            "cc": [{"name": r.get("emailAddress", {}).get("name"), "addr": r.get("emailAddress", {}).get("address")} for r in cc_addrs],
            "subject": data.get("subject", ""),
            "date": data.get("receivedDateTime", ""),
            "body_text": data.get("body", {}).get("content") if data.get("body", {}).get("contentType") == "text" else "",
            "body_html": data.get("body", {}).get("content") if data.get("body", {}).get("contentType") == "html" else "",
            "has_attachments": data.get("hasAttachments", False),
            "importance": data.get("importance"),
            "is_read": data.get("isRead", False),
        }

    def get(self, alias: str, message_id: str) -> dict[str, object]:
        """Get full message by ID."""
        response = self._request("GET", f"{GRAPH_BASE}/messages/{message_id}", alias)
        data = response.json()
        return self._parse_message(data)

    def send(
        self,
        alias: str,
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
        """Send a message via Graph API."""
        profile = self.profile(alias)
        from_addr = profile.get("email", "")

        mime_msg = build_mime(
            from_addr=from_addr,
            to=to,
            cc=cc or [],
            bcc=bcc or [],
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            in_reply_to=in_reply_to,
            references=references,
        )

        # Graph requires MIME as base64 in "message" property
        raw = base64.b64encode(mime_msg.as_bytes()).decode("ascii")

        response = self._request(
            "POST",
            f"{GRAPH_BASE}/sendMail",
            alias,
            json_data={"message": {"raw": raw}, "saveToSentItems": "true"},
        )
        # Graph sendMail returns 202 Accepted with no body on success
        return {"id": "sent", "status": "sent"}

    def draft(
        self,
        alias: str,
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
        """Create a draft via Graph API."""
        profile = self.profile(alias)
        from_addr = profile.get("email", "")

        mime_msg = build_mime(
            from_addr=from_addr,
            to=to,
            cc=cc or [],
            bcc=bcc or [],
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            in_reply_to=in_reply_to,
            references=references,
        )

        raw = base64.b64encode(mime_msg.as_bytes()).decode("ascii")

        response = self._request(
            "POST",
            f"{GRAPH_BASE}/messages",
            alias,
            json_data={"raw": raw},
        )
        data = response.json()
        return {"id": data.get("id")}

    def move(self, alias: str, message_id: str, destination: str) -> dict[str, object]:
        """Move message to folder (returns new message ID per Graph behavior)."""
        # Use cached folders
        folders = self.folders(alias)
        dest_folder = next((f for f in folders if f["name"].lower() == destination.lower()), None)
        if not dest_folder:
            raise ValueError(f"folder not found: {destination}")

        response = self._request(
            "POST",
            f"{GRAPH_BASE}/messages/{message_id}/move",
            alias,
            json_data={"destinationId": dest_folder["id"]},
        )
        data = response.json()
        # Graph returns the moved message with NEW ID
        return {"id": data.get("id"), "folder": destination}

    def trash(self, alias: str, message_id: str) -> dict[str, object]:
        """Move message to Deleted Items (uses cached folders)."""
        folders = self.folders(alias)
        deleted = next((f for f in folders if f["name"].lower() in ("deleted items", "trash")), None)
        if not deleted:
            raise ValueError("Deleted Items folder not found")
        return self.move(alias, message_id, deleted["name"])

    def get_attachment(self, alias: str, message_id: str, attachment_id: str) -> bytes:
        """Download an attachment."""
        response = self._request(
            "GET",
            f"{GRAPH_BASE}/messages/{message_id}/attachments/{attachment_id}/$value",
            alias,
        )
        return response.content


