"""Microsoft Graph People/Contacts adapter for Mailhub M4."""

from __future__ import annotations

from typing import Any

import httpx

from .contacts import (
    Address,
    Contact,
    ContactGroup,
    ContactNotFound,
    Email,
    Name,
    Organization,
    Phone,
    Photo,
    ContactSource,
)
from .core import Core


GRAPH_BASE = "https://graph.microsoft.com/v1.0/me"


class GraphPeopleAdapter:
    """Microsoft Graph People/Contacts adapter (synchronous)."""

    def __init__(self, core: Core) -> None:
        self._core = core
        self._client: httpx.Client | None = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=30.0)
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def _auth_header(self, alias: str) -> dict[str, str]:
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

                if response.status_code == 401:
                    if attempt == 0:
                        self._core._refresh_access_token(alias)
                        request_headers = self._auth_header(alias)
                        if headers:
                            request_headers.update(headers)
                        continue
                    response.raise_for_status()

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

    def _parse_address(self, data: dict | None) -> Address | None:
        if not data:
            return None
        return Address(
            street=data.get("street"),
            city=data.get("city"),
            region=data.get("state"),
            postal_code=data.get("postalCode"),
            country=data.get("countryOrRegion"),
            type=data.get("type", "other"),
        )

    def _parse_contact(self, data: dict) -> Contact:
        # Parse name
        names = ()
        if data.get("givenName") or data.get("surname"):
            names = (Name(
                given=data.get("givenName"),
                family=data.get("surname"),
                middle=data.get("middleName"),
                display=data.get("displayName"),
            ),)

        # Parse emails
        emails = tuple(
            Email(value=e.get("address", ""), type=e.get("type", "other"))
            for e in data.get("emailAddresses", [])
        )

        # Parse phones
        phones = tuple(
            Phone(value=p.get("number", ""), type=p.get("type", "other"))
            for p in data.get("phones", [])
        )

        # Parse addresses - handle both dict and list formats
        home_addr = data.get("homeAddress")
        business_addr = data.get("businessAddress")
        other_addr = data.get("otherAddress")
        addresses_list = []
        for addr in (home_addr, business_addr, other_addr):
            if addr:
                addresses_list.append(self._parse_address(addr))
        addresses = tuple(a for a in addresses_list if a)

        # Parse organizations
        organizations = ()
        if data.get("companyName") or data.get("jobTitle"):
            organizations = (Organization(
                name=data.get("companyName", ""),
                title=data.get("jobTitle"),
                department=data.get("department"),
            ),)

        # Parse birthday
        birthday = None
        if data.get("birthday"):
            try:
                from datetime import date
                parts = data["birthday"].split("-")
                if len(parts) == 3:
                    birthday = date(int(parts[0]), int(parts[1]), int(parts[2]))
            except Exception:
                pass

        # Notes
        notes = data.get("personalNotes") or data.get("bodyPreview")

        return Contact(
            id=data.get("id", ""),
            etag=data.get("@odata.etag"),
            names=names,
            emails=emails,
            phones=phones,
            addresses=addresses,
            organizations=organizations,
            birthday=birthday,
            notes=notes,
            source=ContactSource.GRAPH,
        )

    # --- Public API ---

    def contacts(
        self,
        alias: str,
        folder_id: str | None = None,
        top: int = 100,
        skip: int = 0,
    ) -> dict[str, Any]:
        """List contacts."""
        params = {
            "$top": top,
            "$skip": skip,
            "$orderby": "givenName,surname",
        }
        
        url = f"{GRAPH_BASE}/contacts"
        if folder_id:
            url = f"{GRAPH_BASE}/contactFolders/{folder_id}/contacts"

        response = self._request("GET", url, alias, params=params)
        data = response.json()
        contacts = [self._parse_contact(c) for c in data.get("value", [])]
        return {
            "contacts": contacts,
            "next_page_token": data.get("@odata.nextLink", "").split("$skiptoken=")[-1] if "@odata.nextLink" in data else None,
        }

    def get_contact(self, alias: str, contact_id: str) -> Contact:
        """Get a single contact."""
        response = self._request("GET", f"{GRAPH_BASE}/contacts/{contact_id}", alias)
        data = response.json()
        return self._parse_contact(data)

    def create_contact(self, alias: str, contact: Contact, confirm: bool = False) -> Contact:
        """Create a contact (requires confirm)."""
        if not confirm:
            raise ValueError("create contact requires confirm=True")

        body = self._contact_to_body(contact)
        response = self._request("POST", f"{GRAPH_BASE}/contacts", alias, json_data=body)
        data = response.json()
        return self._parse_contact(data)

    def update_contact(self, alias: str, contact_id: str, contact: Contact, confirm: bool = False) -> Contact:
        """Update a contact (requires confirm)."""
        if not confirm:
            raise ValueError("update contact requires confirm=True")

        body = self._contact_to_body(contact)
        response = self._request("PATCH", f"{GRAPH_BASE}/contacts/{contact_id}", alias, json_data=body)
        data = response.json()
        return self._parse_contact(data)

    def delete_contact(self, alias: str, contact_id: str, confirm: bool = False) -> None:
        """Delete a contact (requires confirm)."""
        if not confirm:
            raise ValueError("delete contact requires confirm=True")

        self._request("DELETE", f"{GRAPH_BASE}/contacts/{contact_id}", alias)

    def contact_folders(self, alias: str) -> list[ContactGroup]:
        """List contact folders."""
        response = self._request("GET", f"{GRAPH_BASE}/contactFolders", alias)
        data = response.json()
        folders = []
        for f in data.get("value", []):
            folders.append(ContactGroup(
                id=f["id"],
                name=f.get("displayName", ""),
            ))
        return folders

    def create_folder(self, alias: str, name: str, confirm: bool = False) -> ContactGroup:
        """Create a contact folder (requires confirm)."""
        if not confirm:
            raise ValueError("create folder requires confirm=True")

        body = {"displayName": name}
        response = self._request("POST", f"{GRAPH_BASE}/contactFolders", alias, json_data=body)
        data = response.json()
        return ContactGroup(
            id=data["id"],
            name=data.get("displayName", ""),
        )

    def _contact_to_body(self, contact: Contact) -> dict[str, Any]:
        body: dict[str, Any] = {}

        if contact.names:
            n = contact.names[0]
            body["givenName"] = n.given
            body["surname"] = n.family
            body["middleName"] = n.middle

        if contact.emails:
            body["emailAddresses"] = [
                {"address": e.value, "name": e.type} for e in contact.emails
            ]

        if contact.phones:
            body["phones"] = [
                {"type": p.type, "number": p.value} for p in contact.phones
            ]

        if contact.addresses:
            # Split into home and business
            for a in contact.addresses:
                if a.type == "home":
                    body["homeAddress"] = {
                        "street": a.street,
                        "city": a.city,
                        "state": a.region,
                        "postalCode": a.postal_code,
                        "countryOrRegion": a.country,
                    }
                else:
                    body["businessAddress"] = {
                        "street": a.street,
                        "city": a.city,
                        "state": a.region,
                        "postalCode": a.postal_code,
                        "countryOrRegion": a.country,
                    }

        if contact.organizations:
            o = contact.organizations[0]
            body["companyName"] = o.name
            body["jobTitle"] = o.title
            body["department"] = o.department

        if contact.birthday:
            body["birthday"] = contact.birthday.isoformat()

        if contact.notes:
            body["personalNotes"] = contact.notes

        return body


