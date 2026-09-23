"""PKCE OAuth authorization-code flow for Google and Microsoft."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import tempfile
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx


Provider = Literal["gmail", "graph"]


REDIRECT_URI = "http://localhost:8788"

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_SCOPE = "https://www.googleapis.com/auth/gmail.modify"

GRAPH_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
GRAPH_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
GRAPH_SCOPE = "offline_access Mail.ReadWrite Mail.Send User.Read MailboxSettings.ReadWrite"


class ReauthNeeded(Exception):
    """Raised when a refresh token is invalid or revoked and interactive re-auth is required."""


@dataclass(frozen=True)
class PKCE:
    """PKCE code verifier and challenge pair."""
    code_verifier: str
    code_challenge: str


@dataclass(frozen=True)
class AuthState:
    """OAuth authorization state with PKCE and CSRF protection."""
    state: str
    provider: Provider
    alias: str
    pkce: PKCE


def _generate_code_verifier() -> str:
    """Generate a random PKCE code verifier (43-128 chars, URL-safe)."""
    return secrets.token_urlsafe(96)[:128]


def _code_challenge(verifier: str) -> str:
    """Compute S256 code challenge from verifier."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def generate_pkce() -> PKCE:
    """Generate a new PKCE verifier/challenge pair."""
    verifier = _generate_code_verifier()
    return PKCE(code_verifier=verifier, code_challenge=_code_challenge(verifier))


def auth_url(provider: Provider, client_id: str, email: str, alias: str) -> tuple[str, AuthState]:
    """
    Generate an authorization URL with PKCE and random state.

    Returns the URL and the AuthState to persist for later validation.
    """
    pkce = generate_pkce()
    state = secrets.token_urlsafe(32)
    auth_state = AuthState(state=state, provider=provider, alias=alias, pkce=pkce)

    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": GOOGLE_SCOPE if provider == "gmail" else GRAPH_SCOPE,
        "state": state,
        "code_challenge": pkce.code_challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
    }
    if provider == "gmail":
        params["login_hint"] = email

    base = GOOGLE_AUTH_URL if provider == "gmail" else GRAPH_AUTH_URL
    url = f"{base}?{urllib.parse.urlencode(params)}"
    return url, auth_state


def parse_redirect(text: str) -> tuple[str, str | None]:
    """
    Extract authorization code and state from a redirect URL or bare code.

    Returns (code, state) where state may be None if not present.
    """
    text = text.strip()
    if "://" in text:
        parsed = urllib.parse.urlparse(text)
        query = urllib.parse.parse_qs(parsed.query)
        code = query.get("code", [None])[0]
        state = query.get("state", [None])[0]
        if code is None:
            raise ValueError("no authorization code in redirect URL")
        return code, state
    return text, None


def check_state(state: str, provider: Provider, alias: str, stored: AuthState) -> PKCE:
    """
    Validate the returned state against stored state.

    Returns the PKCE verifier for token exchange.
    Raises ValueError if state is invalid or mismatched.
    """
    if state != stored.state:
        raise ValueError("state mismatch")
    if stored.provider != provider:
        raise ValueError("provider mismatch")
    if stored.alias != alias:
        raise ValueError("alias mismatch")
    return stored.pkce


def _token_request(
    token_url: str,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
    grant_type: str,
    extra: dict[str, str] | None = None,
) -> dict[str, object]:
    """Send a token request and return parsed JSON."""
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
        "grant_type": grant_type,
    }
    if extra:
        data.update(extra)

    with httpx.Client(timeout=30.0) as client:
        response = client.post(token_url, data=data)
        response.raise_for_status()
        return response.json()


def exchange(
    provider: Provider,
    client_id: str,
    client_secret: str,
    code: str,
    code_verifier: str,
) -> dict[str, object]:
    """
    Exchange authorization code for access/refresh tokens.

    Returns the token response dict (access_token, refresh_token, expires_in, etc.).
    """
    token_url = GOOGLE_TOKEN_URL if provider == "gmail" else GRAPH_TOKEN_URL
    return _token_request(
        token_url=token_url,
        client_id=client_id,
        client_secret=client_secret,
        code=code,
        redirect_uri=REDIRECT_URI,
        code_verifier=code_verifier,
        grant_type="authorization_code",
    )


def refresh(
    provider: Provider,
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> dict[str, object]:
    """
    Refresh an access token using a refresh token.

    Returns the token response dict.
    Raises ReauthNeeded if the refresh token is invalid/revoked.
    """
    token_url = GOOGLE_TOKEN_URL if provider == "gmail" else GRAPH_TOKEN_URL
    try:
        return _token_request(
            token_url=token_url,
            client_id=client_id,
            client_secret=client_secret,
            code=refresh_token,
            redirect_uri=REDIRECT_URI,
            code_verifier="",  # not used for refresh_token grant
            grant_type="refresh_token",
            extra={"refresh_token": refresh_token},
        )
    except httpx.HTTPStatusError as error:
        if error.response.status_code in (400, 401):
            raise ReauthNeeded("refresh token invalid or revoked") from error
        raise


# Provider constants for reference
REDIRECT_URI = "http://localhost:8788"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_SCOPE = "https://www.googleapis.com/auth/gmail.modify"
GRAPH_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
GRAPH_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
GRAPH_SCOPE = "offline_access Mail.ReadWrite Mail.Send User.Read MailboxSettings.ReadWrite"
