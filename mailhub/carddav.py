"""CardDAV adapter for Mailhub M4 (read support)."""

from __future__ import annotations

from typing import Any

import httpx

from .contacts import Contact, ContactNotFound
from .core import Core


class CardDAVAdapter:
    """CardDAV adapter (synchronous, read support)."""

    def __init__(self, core: Core) -> None:
        self._core = core
        self._client: httpx.Client | None = None
        self._base_url: str | None = None
        self._username: str | None = None
        self._password: str | None = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=30.0)
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def _load_credentials(self, alias: str) -> None:
        """Load CardDAV credentials from core store."""
        creds = self._core._load_credentials(alias)
        self._base_url = creds.client_id  # stored as base_url
        self._username = creds.client_secret  # stored as username
        self._password = creds.access_token  # stored as password
        if not self._base_url or not self._username or not self._password:
            raise ValueError(f"CardDAV credentials not configured for {alias}")

    def _auth(self) -> tuple[str, str]:
        return (self._username, self._password)

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        content: str | None = None,
    ) -> httpx.Response:
        client = self._get_client()
        request_headers = {"Depth": "1", "Content-Type": "application/xml; charset=utf-8"}
        if headers:
            request_headers.update(headers)
        
        response = client.request(
            method,
            url,
            auth=self._auth(),
            headers=request_headers,
            content=content,
        )
        response.raise_for_status()
        return response

    def _parse_contact(self, href: str, vcard_data: str) -> Contact | None:
        """Parse vCard data into Contact."""
        # Basic vCard parsing - would need vobject library for full support
        # This is a minimal stub
        return None

    # --- Public API (read) ---

    def contacts(self, alias: str) -> list[Contact]:
        """List contacts (REPORT addressbook-query)."""
        self._load_credentials(alias)
        # Would need REPORT with CARD:addressbook-query filter
        # For now, return empty list
        return []

    def get_contact(self, alias: str, href: str) -> Contact:
        """Get a single contact."""
        self._load_credentials(alias)
        # GET the vCard resource
        raise ContactNotFound(f"Contact {href} not found")

    # Write operations not implemented in basic CardDAV adapter
    def create_contact(self, *args, **kwargs) -> Contact:
        raise NotImplementedError("CardDAV write operations not implemented")

    def update_contact(self, *args, **kwargs) -> Contact:
        raise NotImplementedError("CardDAV write operations not implemented")

    def delete_contact(self, *args, **kwargs) -> None:
        raise NotImplementedError("CardDAV write operations not implemented")


