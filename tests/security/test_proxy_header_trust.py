"""
Security regression tests — proxy header trust boundary.

Invariant: X-User-Id and X-User-Role headers are trusted ONLY from configured
trusted CIDRs. An attacker sending these headers from an external IP must get
(None, None) back — the headers must be silently ignored, not acted upon.

This test suite covers the injection scenario where an attacker bypasses the
Next.js dashboard and directly calls the FastAPI backend with forged session
headers claiming to be admin.
"""
from __future__ import annotations

import pytest

from tests.security.conftest import _make_request

pytestmark = pytest.mark.security


# ---------------------------------------------------------------------------
# Header extraction gating
# ---------------------------------------------------------------------------

class TestProxyHeaderExtraction:
    """_get_session_user must gate on client IP, not just header presence."""

    def test_admin_header_from_external_ip_is_ignored(self) -> None:
        """Attacker sends X-User-Id: admin from 1.2.3.4 — must be ignored."""
        from langsight.api.dependencies import _get_session_user

        req = _make_request(
            client_ip="1.2.3.4",
            headers={"X-User-Id": "admin-spoof", "X-User-Role": "admin"},
            trusted_cidrs="127.0.0.1/32,::1/128",
        )
        user_id, user_role = _get_session_user(req)
        assert user_id is None, "Spoofed header from untrusted IP must be ignored"
        assert user_role is None

    def test_admin_header_from_docker_private_range_is_accepted(self) -> None:
        """Dashboard proxy in Docker (172.18.0.x) must be trusted when CIDR configured."""
        from langsight.api.dependencies import _get_session_user

        req = _make_request(
            client_ip="172.18.0.5",
            headers={"X-User-Id": "real-user", "X-User-Role": "admin"},
            trusted_cidrs="127.0.0.1/32,172.16.0.0/12",
        )
        user_id, user_role = _get_session_user(req)
        assert user_id == "real-user"
        assert user_role == "admin"

    def test_admin_header_from_loopback_is_trusted(self) -> None:
        from langsight.api.dependencies import _get_session_user

        req = _make_request(
            client_ip="127.0.0.1",
            headers={"X-User-Id": "dashboard-user", "X-User-Role": "viewer"},
        )
        user_id, user_role = _get_session_user(req)
        assert user_id == "dashboard-user"
        assert user_role == "viewer"

    def test_role_without_user_id_grants_nothing(self) -> None:
        """X-User-Role alone (no User-Id) must not grant admin or any identity."""
        from langsight.api.dependencies import _get_session_user

        req = _make_request(
            client_ip="127.0.0.1",
            headers={"X-User-Role": "admin"},   # no X-User-Id
        )
        user_id, user_role = _get_session_user(req)
        assert user_id is None

    def test_user_id_without_role_returns_none_role(self) -> None:
        """X-User-Id without X-User-Role must not default to any elevated role."""
        from langsight.api.dependencies import _get_session_user

        req = _make_request(
            client_ip="127.0.0.1",
            headers={"X-User-Id": "partial-header-user"},  # no X-User-Role
        )
        user_id, user_role = _get_session_user(req)
        # user_id may be set but role must be None — cannot assume admin
        assert user_role is None

    def test_empty_user_id_header_is_ignored(self) -> None:
        from langsight.api.dependencies import _get_session_user

        req = _make_request(
            client_ip="127.0.0.1",
            headers={"X-User-Id": "", "X-User-Role": "admin"},
        )
        user_id, _ = _get_session_user(req)
        assert not user_id  # empty string or None — either way, not trusted


# ---------------------------------------------------------------------------
# Spoofed headers do not bypass verify_api_key
# ---------------------------------------------------------------------------

class TestSpoofedHeadersDoNotBypassAuth:
    """Even if headers arrive from a trusted IP, auth still needs a valid credential
    when keys are configured. Session headers are auth, not a key bypass."""

    async def test_spoofed_admin_headers_from_untrusted_ip_still_need_key(self) -> None:
        """Request from external IP with admin headers and NO key → 401."""
        from fastapi import HTTPException

        from langsight.api.dependencies import verify_api_key

        req = _make_request(
            client_ip="8.8.8.8",  # external
            headers={"X-User-Id": "attacker", "X-User-Role": "admin"},
            api_keys=["legit-key"],  # auth is enabled
        )
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(request=req, api_key=None)
        assert exc_info.value.status_code == 401

    async def test_valid_session_from_trusted_ip_does_not_need_api_key(self) -> None:
        """Dashboard user via loopback proxy — no X-API-Key needed, session is auth."""
        from langsight.api.dependencies import verify_api_key

        req = _make_request(
            client_ip="127.0.0.1",
            headers={"X-User-Id": "user-123", "X-User-Role": "viewer"},
            api_keys=["some-configured-key"],
        )
        # Session from trusted proxy is sufficient — must not raise
        await verify_api_key(request=req, api_key=None)


# ---------------------------------------------------------------------------
# IP boundary edge cases
# ---------------------------------------------------------------------------

class TestIpBoundaryEdgeCases:
    def test_cidr_boundary_just_inside_is_trusted(self) -> None:
        from langsight.api.dependencies import _get_session_user

        # 10.0.0.1 is inside 10.0.0.0/8
        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-User-Id": "inside-user", "X-User-Role": "viewer"},
            trusted_cidrs="10.0.0.0/8",
        )
        user_id, _ = _get_session_user(req)
        assert user_id == "inside-user"

    def test_cidr_boundary_just_outside_is_untrusted(self) -> None:
        from langsight.api.dependencies import _get_session_user

        # 11.0.0.1 is outside 10.0.0.0/8
        req = _make_request(
            client_ip="11.0.0.1",
            headers={"X-User-Id": "outside-user", "X-User-Role": "admin"},
            trusted_cidrs="10.0.0.0/8",
        )
        user_id, _ = _get_session_user(req)
        assert user_id is None

    def test_no_client_ip_is_not_trusted(self) -> None:
        """Request with no client information must never be treated as proxy."""
        from langsight.api.dependencies import _is_proxy_request

        req = _make_request(client_ip="")
        req.client = None  # completely absent
        assert not _is_proxy_request(req)
