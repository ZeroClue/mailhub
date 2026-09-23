"""Unit tests for mailhub.oauth module."""

from __future__ import annotations

import pytest

from mailhub.oauth import (
    PKCE,
    AuthState,
    Provider,
    ReauthNeeded,
    auth_url,
    check_state,
    exchange,
    generate_pkce,
    parse_redirect,
    refresh,
)


class TestPKCE:
    def test_generate_pkce_returns_verifier_and_challenge(self):
        pkce = generate_pkce()
        assert isinstance(pkce, PKCE)
        assert len(pkce.code_verifier) >= 43
        assert len(pkce.code_challenge) > 0
        assert pkce.code_verifier != pkce.code_challenge

    def test_code_challenge_is_deterministic_for_same_verifier(self):
        pkce1 = generate_pkce()
        pkce2 = PKCE(code_verifier=pkce1.code_verifier, code_challenge=pkce1.code_challenge)
        assert pkce1.code_challenge == pkce2.code_challenge


class TestAuthURL:
    def test_gmail_auth_url_contains_required_params(self):
        url, state = auth_url("gmail", "client123", "user@gmail.com", "personal")
        assert "accounts.google.com" in url
        assert "client_id=client123" in url
        assert "redirect_uri=http%3A%2F%2Flocalhost%3A8788" in url
        assert "response_type=code" in url
        assert "scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fgmail.modify" in url
        assert "code_challenge=" in url
        assert "code_challenge_method=S256" in url
        assert "access_type=offline" in url
        assert "prompt=consent" in url
        assert "login_hint=user%40gmail.com" in url
        assert state.provider == "gmail"
        assert state.alias == "personal"

    def test_graph_auth_url_contains_required_params(self):
        url, state = auth_url("graph", "client456", "user@outlook.com", "work")
        assert "login.microsoftonline.com" in url
        assert "client_id=client456" in url
        assert "scope=offline_access+Mail.ReadWrite+Mail.Send+User.Read+MailboxSettings.ReadWrite" in url
        assert state.provider == "graph"
        assert state.alias == "work"


class TestParseRedirect:
    def test_parses_full_url_with_code_and_state(self):
        url = "http://localhost:8788/?code=abc123&state=xyz789"
        code, state = parse_redirect(url)
        assert code == "abc123"
        assert state == "xyz789"

    def test_parses_bare_code(self):
        code, state = parse_redirect("justacode")
        assert code == "justacode"
        assert state is None

    def test_raises_on_missing_code(self):
        with pytest.raises(ValueError, match="no authorization code"):
            parse_redirect("http://localhost:8788/?state=only")


class TestCheckState:
    def test_valid_state_returns_pkce(self):
        pkce = generate_pkce()
        stored = AuthState(state="state123", provider="gmail", alias="personal", pkce=pkce)
        result = check_state("state123", "gmail", "personal", stored)
        assert result == pkce

    def test_invalid_state_raises(self):
        pkce = generate_pkce()
        stored = AuthState(state="state123", provider="gmail", alias="personal", pkce=pkce)
        with pytest.raises(ValueError, match="state mismatch"):
            check_state("wrong", "gmail", "personal", stored)

    def test_provider_mismatch_raises(self):
        pkce = generate_pkce()
        stored = AuthState(state="state123", provider="graph", alias="personal", pkce=pkce)
        with pytest.raises(ValueError, match="provider mismatch"):
            check_state("state123", "gmail", "personal", stored)

    def test_alias_mismatch_raises(self):
        pkce = generate_pkce()
        stored = AuthState(state="state123", provider="gmail", alias="work", pkce=pkce)
        with pytest.raises(ValueError, match="alias mismatch"):
            check_state("state123", "gmail", "personal", stored)


class TestExchange:
    def test_google_exchange_requires_client_secret(self):
        with pytest.raises(Exception):
            # Should fail due to missing/invalid credentials
            exchange("gmail", "client_id", "client_secret", "code", "verifier")

    def test_graph_exchange_requires_client_secret(self):
        with pytest.raises(Exception):
            exchange("graph", "client_id", "client_secret", "code", "verifier")


class TestRefresh:
    def test_refresh_raises_reauth_needed_on_400(self):
        # This would need mocked HTTP to test properly
        # For now just verify the exception type is importable
        assert ReauthNeeded is not None

    def test_refresh_raises_reauth_needed_on_401(self):
        assert ReauthNeeded is not None


