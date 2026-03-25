"""Unit tests for sdk/_ids.py and MCPClientProxy.session_id / wrap() auto-generation.

Covers:
- _new_session_id() format and uniqueness
- MCPClientProxy.session_id property
- LangSightClient.wrap() auto-generates a session_id when none is provided
- LangSightClient.wrap() uses the caller-supplied session_id when provided
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock

import pytest

from langsight.sdk._ids import _new_session_id
from langsight.sdk.client import LangSightClient, MCPClientProxy


# ---------------------------------------------------------------------------
# _new_session_id
# ---------------------------------------------------------------------------

_HEX32_RE = re.compile(r"^[0-9a-f]{32}$")


@pytest.mark.unit
class TestNewSessionId:
    def test_returns_32_hex_chars(self) -> None:
        sid = _new_session_id()
        assert _HEX32_RE.match(sid), f"Expected 32 hex chars, got {sid!r}"

    def test_no_dashes(self) -> None:
        sid = _new_session_id()
        assert "-" not in sid

    def test_unique_on_each_call(self) -> None:
        ids = {_new_session_id() for _ in range(50)}
        assert len(ids) == 50, "All generated IDs must be unique"

    def test_url_safe(self) -> None:
        """Only hex chars — safe in URLs and HTTP headers without encoding."""
        for _ in range(20):
            sid = _new_session_id()
            assert _HEX32_RE.match(sid)


# ---------------------------------------------------------------------------
# MCPClientProxy.session_id property
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMCPClientProxySessionId:
    def _make_proxy(self, session_id: str = "abc123") -> MCPClientProxy:
        client = LangSightClient(url="http://localhost:8000")
        mock_mcp = MagicMock()
        return MCPClientProxy(
            mock_mcp,
            langsight=client,
            session_id=session_id,
        )

    def test_session_id_returns_stored_value(self) -> None:
        proxy = self._make_proxy(session_id="my-session-id")
        assert proxy.session_id == "my-session-id"

    def test_session_id_is_string(self) -> None:
        proxy = self._make_proxy()
        assert isinstance(proxy.session_id, str)

    def test_session_id_does_not_expose_private_attribute_via_getattr(self) -> None:
        """__getattr__ forwards to the wrapped client — session_id must be
        a proper @property, not just a forwarded attribute."""
        proxy = self._make_proxy(session_id="check-isolation")
        # Access via property, not via the wrapped mock client
        assert proxy.session_id == "check-isolation"


# ---------------------------------------------------------------------------
# LangSightClient.wrap() — session_id handling
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWrapSessionIdAutoGeneration:
    def _client(self) -> LangSightClient:
        return LangSightClient(url="http://localhost:8000")

    def test_wrap_without_session_id_auto_generates_one(self) -> None:
        client = self._client()
        proxy = client.wrap(MagicMock(), server_name="srv")
        sid = proxy.session_id
        assert sid is not None
        assert _HEX32_RE.match(sid), f"Auto-generated session_id must be 32 hex chars, got {sid!r}"

    def test_wrap_with_explicit_session_id_uses_provided(self) -> None:
        client = self._client()
        proxy = client.wrap(MagicMock(), server_name="srv", session_id="my-explicit-id")
        assert proxy.session_id == "my-explicit-id"

    def test_wrap_auto_generates_different_session_ids_each_call(self) -> None:
        client = self._client()
        p1 = client.wrap(MagicMock(), server_name="srv")
        p2 = client.wrap(MagicMock(), server_name="srv")
        assert p1.session_id != p2.session_id

    def test_wrap_preserves_server_name(self) -> None:
        client = self._client()
        proxy = client.wrap(MagicMock(), server_name="my-postgres-mcp")
        assert proxy._server_name == "my-postgres-mcp"

    def test_wrap_inherits_client_project_id_when_not_overridden(self) -> None:
        client = LangSightClient(url="http://localhost:8000", project_id="proj-global")
        proxy = client.wrap(MagicMock(), server_name="srv")
        assert proxy._project_id == "proj-global"

    def test_wrap_overrides_project_id_when_specified(self) -> None:
        client = LangSightClient(url="http://localhost:8000", project_id="proj-global")
        proxy = client.wrap(MagicMock(), server_name="srv", project_id="proj-local")
        assert proxy._project_id == "proj-local"

    def test_wrap_inherits_client_redact_payloads_when_not_overridden(self) -> None:
        client = LangSightClient(url="http://localhost:8000", redact_payloads=True)
        proxy = client.wrap(MagicMock(), server_name="srv")
        assert proxy._redact_payloads is True

    def test_wrap_overrides_redact_payloads_when_specified(self) -> None:
        client = LangSightClient(url="http://localhost:8000", redact_payloads=True)
        proxy = client.wrap(MagicMock(), server_name="srv", redact_payloads=False)
        assert proxy._redact_payloads is False
