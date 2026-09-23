"""Gmail API adapter - full implementation for M2."""

from __future__ import annotations

import base64
import email
import email.message
import json
import mimetypes
from dataclasses import dataclass
from typing import Any

import httpx

from .core import Core

# Gmail API base URL
GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


@dataclass
class _Attachment:
    """Internal representation of an attachment."""
    attachment_id: str
    filename: str
    mime_type: str
    size: int


class GmailAdapter:
    """Gmail API adapter (synchronous)."""

    def __init__(self, core: Core) -> None:
        self._core = core
        self._client: httpx.Client | None = None

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
                # HTTPStatusError is a subclass of RequestError, but we catch it explicitly
                # to ensure retry logic applies to 429/5xx that raise_for_status() would catch
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
        response = self._request("GET", f"{GMAIL_BASE}/profile", alias)
        data = response.json()
        return {
            "email": data.get("emailAddress"),
            "provider": "gmail",
            "messages_total": data.get("messagesTotal"),
            "threads_total": data.get("threadsTotal"),
            "history_id": data.get("historyId"),
        }

    def folders(self, alias: str) -> list[dict[str, object]]:
        """List labels (Gmail uses labels as folders)."""
        response = self._request("GET", f"{GMAIL_BASE}/labels", alias)
        data = response.json()
        labels = []
        for label in data.get("labels", []):
            labels.append({
                "id": label["id"],
                "name": label["name"],
                "type": label["type"],
                "messages_total": label.get("messagesTotal"),
                "messages_unread": label.get("messagesUnread"),
                "threads_total": label.get("threadsTotal"),
                "threads_unread": label.get("threadsUnread"),
            })
        return labels

    def search(
        self,
        alias: str,
        query: str,
        *,
        max_results: int = 50,
        page_token: str | None = None,
    ) -> dict[str, object]:
        """Search messages using Gmail query syntax."""
        params = {"maxResults": max_results, "q": query}
        if page_token:
            params["pageToken"] = page_token

        response = self._request("GET", f"{GMAIL_BASE}/messages", alias, params=params)
        data = response.json()

        messages = []
        for msg in data.get("messages", []):
            # Fetch message metadata for each
            msg_detail = self.get(alias, msg["id"])
            messages.append(msg_detail)

        return {
            "messages": messages,
            "next_page_token": data.get("nextPageToken"),
            "result_size_estimate": data.get("resultSizeEstimate"),
        }

    def get(self, alias: str, message_id: str) -> dict[str, object]:
        """Get full message with body and attachments."""
        response = self._request(
            "GET",
            f"{GMAIL_BASE}/messages/{message_id}",
            alias,
            params={"format": "full"},
        )
        data = response.json()

        return self._parse_message(data)

    def _parse_message(self, data: dict) -> dict[str, object]:
        """Parse Gmail API message format."""
        headers = {}
        for header in data.get("payload", {}).get("headers", []):
            headers[header["name"].lower()] = header["value"]

        # Extract body
        body_text = ""
        body_html = ""
        attachments = []

        def extract_parts(part: dict, path: str = ""):
            nonlocal body_text, body_html, attachments
            mime_type = part.get("mimeType", "")
            body = part.get("body", {})

            if body.get("attachmentId"):
                attachments.append(_Attachment(
                    attachment_id=body["attachmentId"],
                    filename=part.get("filename", "attachment"),
                    mime_type=mime_type,
                    size=body.get("size", 0),
                ))
            elif mime_type == "text/plain" and body.get("data"):
                body_text = base64.urlsafe_b64decode(body["data"] + "=" * (-len(body["data"]) % 4)).decode("utf-8", errors="replace")
            elif mime_type == "text/html" and body.get("data"):
                body_html = base64.urlsafe_b64decode(body["data"] + "=" * (-len(body["data"]) % 4)).decode("utf-8", errors="replace")
            elif "parts" in part:
                for i, subpart in enumerate(part["parts"]):
                    extract_parts(subpart, f"{path}.{i}")

        extract_parts(data.get("payload", {}))

        return {
            "id": data.get("id"),
            "thread_id": data.get("threadId"),
            "label_ids": data.get("labelIds", []),
            "snippet": data.get("snippet", ""),
            "from": {"name": headers.get("from", ""), "addr": headers.get("from", "")},
            "to": [{"name": headers.get("to", ""), "addr": headers.get("to", "")}],
            "cc": [{"name": headers.get("cc", ""), "addr": headers.get("cc", "")}] if headers.get("cc") else [],
            "subject": headers.get("subject", ""),
            "date": headers.get("date", ""),
            "body_text": body_text,
            "body_html": body_html,
            "attachments": [
                {"id": a.attachment_id, "filename": a.filename, "mime_type": a.mime_type, "size": a.size}
                for a in attachments
            ],
        }

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
        """Send a message via Gmail API."""
        from .util import build_mime

        # Get sender address from profile
        profile = self.profile(alias)
        from_addr = profile.get("email", "")

        # Build MIME message
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

        # Encode as base64url
        raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("ascii").rstrip("=")

        response = self._request(
            "POST",
            f"{GMAIL_BASE}/messages/send",
            alias,
            json_data={"raw": raw},
        )
        data = response.json()
        return {"id": data.get("id"), "thread_id": data.get("threadId")}

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
        """Create a draft via Gmail API."""
        from .util import build_mime

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

        raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("ascii").rstrip("=")

        response = self._request(
            "POST",
            f"{GMAIL_BASE}/drafts",
            alias,
            json_data={"message": {"raw": raw}},
        )
        data = response.json()
        return {"id": data.get("id")}

    def move(self, alias: str, message_id: str, destination: str) -> dict[str, object]:
        """Move message by adding/removing labels."""
        # Map destination to label operations
        label_map = {
            "inbox": {"add": ["INBOX"], "remove": []},
            "archive": {"add": [], "remove": ["INBOX"]},
            "trash": {"add": ["TRASH"], "remove": ["INBOX"]},
            "spam": {"add": ["SPAM"], "remove": ["INBOX"]},
        }
        ops = label_map.get(destination.lower(), {"add": [], "remove": []})

        response = self._request(
            "POST",
            f"{GMAIL_BASE}/messages/{message_id}/modify",
            alias,
            json_data={
                "addLabelIds": list(ops["add"]),
                "removeLabelIds": list(ops["remove"]),
            },
        )
        data = response.json()
        return {"id": data.get("id"), "label_ids": data.get("labelIds", [])}

    def trash(self, alias: str, message_id: str) -> dict[str, object]:
        """Move message to trash."""
        return self.move(alias, message_id, "trash")

    def get_attachment(self, alias: str, message_id: str, attachment_id: str) -> bytes:
        """Download an attachment."""
        response = self._request(
            "GET",
            f"{GMAIL_BASE}/messages/{message_id}/attachments/{attachment_id}",
            alias,
        )
        data = response.json()
        return base64.urlsafe_b64decode(data.get("data", "") + "=" * (-len(data.get("data", "")) % 4))


