"""Google People API adapter for Mailhub M4."""

from __future__ import annotations

from datetime import date
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


PEOPLE_BASE = "https://people.googleapis.com/v1"


class GooglePeopleAdapter:
    """Google People API adapter (synchronous)."""

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

    def _parse_name(self, data: dict) -> Name | None:
        if not data:
            return None
        return Name(
            given=data.get("givenName"),
            family=data.get("familyName"),
            middle=data.get("middleName"),
            prefix=data.get("honorificPrefix"),
            suffix=data.get("honorificSuffix"),
            display=data.get("displayName"),
        )

    def _parse_email(self, data: dict) -> Email | None:
        if not data:
            return None
        return Email(
            value=data.get("value", ""),
            type=data.get("type", "other"),
            primary=data.get("primary", False),
        )

    def _parse_phone(self, data: dict) -> Phone | None:
        if not data:
            return None
        return Phone(
            value=data.get("value", ""),
            type=data.get("type", "other"),
        )

    def _parse_address(self, data: dict) -> Address | None:
        if not data:
            return None
        return Address(
            street=data.get("streetAddress"),
            city=data.get("city"),
            region=data.get("region"),
            postal_code=data.get("postalCode"),
            country=data.get("country"),
            type=data.get("type", "other"),
            formatted=data.get("formattedValue"),
        )

    def _parse_organization(self, data: dict) -> Organization | None:
        if not data:
            return None
        return Organization(
            name=data.get("name", ""),
            title=data.get("title"),
            department=data.get("department"),
            domain=data.get("domain"),
            type=data.get("type", "work"),
        )

    def _parse_birthday(self, data: dict) -> date | None:
        if not data:
            return None
        # Format: {"date": {"year": 1990, "month": 1, "day": 15}}
        d = data.get("date", {})
        if d.get("year") and d.get("month") and d.get("day"):
            return date(d["year"], d["month"], d["day"])
        return None

    def _parse_photo(self, data: dict) -> Photo | None:
        if not data:
            return None
        return Photo(
            url=data.get("url", ""),
            default=data.get("default", False),
        )

    def _parse_contact(self, data: dict) -> Contact:
        names = tuple(self._parse_name(n) for n in data.get("names", []))
        emails = tuple(self._parse_email(e) for e in data.get("emailAddresses", []))
        phones = tuple(self._parse_phone(p) for p in data.get("phoneNumbers", []))
        addresses = tuple(self._parse_address(a) for a in data.get("addresses", []))
        organizations = tuple(self._parse_organization(o) for o in data.get("organizations", []))
        birthday = self._parse_birthday(data.get("birthdays", [{}])[0]) if data.get("birthdays") else None
        photos = tuple(self._parse_photo(p) for p in data.get("photos", []))

        return Contact(
            id=data.get("resourceName", "").replace("people/", ""),
            etag=data.get("etag"),
            names=names,
            emails=emails,
            phones=phones,
            addresses=addresses,
            organizations=organizations,
            birthday=birthday,
            notes=data.get("biographies", [{}])[0].get("value") if data.get("biographies") else None,
            photos=photos,
            metadata=data.get("metadata", {}),
            source=ContactSource.GOOGLE,
        )

    # --- Public API ---

    def contacts(
        self,
        alias: str,
        page_size: int = 100,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """List contacts (connections)."""
        params = {
            "personFields": "names,emailAddresses,phoneNumbers,addresses,organizations,birthdays,biographies,photos,metadata",
            "pageSize": page_size,
        }
        if page_token:
            params["pageToken"] = page_token

        response = self._request(
            "GET", f"{PEOPLE_BASE}/people/me/connections", alias, params=params
        )
        data = response.json()
        contacts = [self._parse_contact(p) for p in data.get("connections", [])]
        return {
            "contacts": contacts,
            "next_page_token": data.get("nextPageToken"),
        }

    def get_contact(self, alias: str, resource_name: str) -> Contact:
        """Get a single contact by resource name."""
        params = {
            "personFields": "names,emailAddresses,phoneNumbers,addresses,organizations,birthdays,biographies,photos,metadata",
        }
        response = self._request(
            "GET", f"{PEOPLE_BASE}/{resource_name}", alias, params=params
        )
        data = response.json()
        return self._parse_contact(data)

    def create_contact(self, alias: str, contact: Contact, confirm: bool = False) -> Contact:
        """Create a contact (requires confirm)."""
        if not confirm:
            raise ValueError("create contact requires confirm=True")

        body = self._contact_to_body(contact)
        response = self._request(
            "POST", f"{PEOPLE_BASE}/people:createContact", alias, json_data=body
        )
        data = response.json()
        return self._parse_contact(data)

    def update_contact(self, alias: str, resource_name: str, contact: Contact, confirm: bool = False) -> Contact:
        """Update a contact (requires confirm)."""
        if not confirm:
            raise ValueError("update contact requires confirm=True")

        body = self._contact_to_body(contact)
        body["etag"] = contact.etag
        response = self._request(
            "PATCH", f"{PEOPLE_BASE}/{resource_name}", alias, json_data=body
        )
        data = response.json()
        return self._parse_contact(data)

    def delete_contact(self, alias: str, resource_name: str, confirm: bool = False) -> None:
        """Delete a contact (requires confirm)."""
        if not confirm:
            raise ValueError("delete contact requires confirm=True")

        self._request("DELETE", f"{PEOPLE_BASE}/{resource_name}", alias)

    def groups(self, alias: str) -> list[ContactGroup]:
        """List contact groups."""
        response = self._request("GET", f"{PEOPLE_BASE}/contactGroups", alias)
        data = response.json()
        groups = []
        for g in data.get("contactGroups", []):
            groups.append(ContactGroup(
                id=g.get("resourceName", "").replace("contactGroups/", ""),
                name=g.get("name", ""),
                member_count=g.get("memberCount", 0),
            ))
        return groups

    def create_group(self, alias: str, name: str, confirm: bool = False) -> ContactGroup:
        """Create a contact group (requires confirm)."""
        if not confirm:
            raise ValueError("create group requires confirm=True")

        body = {"contactGroup": {"name": name}}
        response = self._request(
            "POST", f"{PEOPLE_BASE}/contactGroups", alias, json_data=body
        )
        data = response.json()
        return ContactGroup(
            id=data.get("resourceName", "").replace("contactGroups/", ""),
            name=data.get("name", ""),
        )

    def add_to_group(self, alias: str, group_id: str, contact_ids: list[str], confirm: bool = False) -> None:
        """Add contacts to group (requires confirm)."""
        if not confirm:
            raise ValueError("add to group requires confirm=True")

        body = {"resourceNamesToAdd": [f"people/{cid}" for cid in contact_ids]}
        self._request(
            "POST",
            f"{PEOPLE_BASE}/contactGroups/{group_id}:modify",
            alias,
            json_data=body,
        )

    def _contact_to_body(self, contact: Contact) -> dict[str, Any]:
        body: dict[str, Any] = {}

        if contact.names:
            n = contact.names[0]
            body["names"] = [{
                "givenName": n.given,
                "familyName": n.family,
                "middleName": n.middle,
                "honorificPrefix": n.prefix,
                "honorificSuffix": n.suffix,
            }]

        if contact.emails:
            body["emailAddresses"] = [
                {"value": e.value, "type": e.type} for e in contact.emails
            ]

        if contact.phones:
            body["phoneNumbers"] = [
                {"value": p.value, "type": p.type} for p in contact.phones
            ]

        if contact.addresses:
            body["addresses"] = [
                {
                    "streetAddress": a.street,
                    "city": a.city,
                    "region": a.region,
                    "postalCode": a.postal_code,
                    "country": a.country,
                    "type": a.type,
                }
                for a in contact.addresses
            ]

        if contact.organizations:
            body["organizations"] = [
                {
                    "name": o.name,
                    "title": o.title,
                    "department": o.department,
                    "domain": o.domain,
                }
                for o in contact.organizations
            ]

        if contact.birthday:
            body["birthdays"] = [{
                "date": {
                    "year": contact.birthday.year,
                    "month": contact.birthday.month,
                    "day": contact.birthday.day,
                }
            }]

        if contact.notes:
            body["biographies"] = [{"value": contact.notes}]

        return body


