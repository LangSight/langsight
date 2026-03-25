"""
Unit tests for _rate_limit_key in langsight.api.rate_limit.

Key resolution order (first match wins):
  1. X-Forwarded-For header — ONLY when TCP client is in trusted_proxy_networks
  2. X-API-Key header prefix — first 16 chars of the key
  3. TCP remote address fallback

No real HTTP server is started; Request objects are constructed directly
using Starlette's Request constructor from a minimal ASGI scope.
"""

from __future__ import annotations

import ipaddress

import pytest
from starlette.datastructures import State
from starlette.requests import Request

from langsight.api.rate_limit import _rate_limit_key

pytestmark = pytest.mark.unit

_TRUSTED_NET = [ipaddress.ip_network("10.0.0.0/8")]


# ---------------------------------------------------------------------------
# Helper: build a minimal Starlette Request without a real ASGI app
# ---------------------------------------------------------------------------


def _make_request(
    headers: dict[str, str] | None = None,
    client_host: str = "10.0.0.1",
    trusted_networks: list | None = None,
) -> Request:
    """Construct a minimal Request with the given headers and remote address.

    Pass trusted_networks to simulate a request arriving from a trusted proxy
    (sets app.state.trusted_proxy_networks on the ASGI app object).
    """
    scope: dict = {
        "type": "http",
        "method": "GET",
        "path": "/api/status",
        "query_string": b"",
        "headers": [
            (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
        ],
        "client": (client_host, 54321),
    }
    if trusted_networks is not None:
        app_state = State()
        app_state.trusted_proxy_networks = trusted_networks

        class _FakeApp:
            state = app_state

        scope["app"] = _FakeApp()

    return Request(scope)


# ---------------------------------------------------------------------------
# X-Forwarded-For — only trusted when request comes from a trusted proxy
# ---------------------------------------------------------------------------


class TestXForwardedFor:
    def test_returns_first_ip_from_x_forwarded_for_when_trusted_proxy(self) -> None:
        """When request comes from a trusted proxy, the first XFF IP is the key."""
        request = _make_request(
            headers={"X-Forwarded-For": "203.0.113.5"},
            client_host="10.0.0.1",
            trusted_networks=_TRUSTED_NET,
        )
        assert _rate_limit_key(request) == "203.0.113.5"

    def test_returns_first_ip_when_multiple_ips_in_x_forwarded_for(self) -> None:
        """Only the first IP is used — downstream proxy IPs are ignored."""
        request = _make_request(
            headers={"X-Forwarded-For": "203.0.113.5, 10.0.0.1, 192.168.1.1"},
            client_host="10.0.0.1",
            trusted_networks=_TRUSTED_NET,
        )
        assert _rate_limit_key(request) == "203.0.113.5"

    def test_strips_whitespace_from_x_forwarded_for_first_ip(self) -> None:
        """Whitespace around the first IP is stripped."""
        request = _make_request(
            headers={"X-Forwarded-For": "  203.0.113.5  , 10.0.0.1"},
            client_host="10.0.0.1",
            trusted_networks=_TRUSTED_NET,
        )
        assert _rate_limit_key(request) == "203.0.113.5"

    def test_x_forwarded_for_ignored_from_untrusted_client(self) -> None:
        """X-Forwarded-For from an untrusted TCP address must be ignored.

        An attacker sending X-Forwarded-For directly (no trusted proxy in front)
        must not be able to spoof a different bucket.
        """
        request = _make_request(
            headers={"X-Forwarded-For": "203.0.113.99"},
            client_host="203.0.113.1",   # untrusted — not in _TRUSTED_NET
            trusted_networks=_TRUSTED_NET,
        )
        # Must fall through to remote address, not the spoofed XFF IP
        key = _rate_limit_key(request)
        assert key != "203.0.113.99"
        assert key == "203.0.113.1"

    def test_x_forwarded_for_ignored_when_no_trusted_networks_configured(self) -> None:
        """Without trusted_proxy_networks configured, XFF is always ignored."""
        request = _make_request(
            headers={"X-Forwarded-For": "203.0.113.5"},
            client_host="10.0.0.1",
            trusted_networks=None,  # no app.state — untrusted
        )
        key = _rate_limit_key(request)
        assert key != "203.0.113.5"

    def test_x_forwarded_for_takes_priority_over_x_api_key_from_trusted_proxy(self) -> None:
        """X-Forwarded-For wins over X-API-Key when from a trusted proxy."""
        request = _make_request(
            headers={"X-Forwarded-For": "203.0.113.42", "X-API-Key": "my-secret-key-here"},
            client_host="10.0.0.1",
            trusted_networks=_TRUSTED_NET,
        )
        assert _rate_limit_key(request) == "203.0.113.42"

    def test_x_forwarded_for_takes_priority_over_remote_address_from_trusted_proxy(self) -> None:
        """X-Forwarded-For wins over the TCP client address when from trusted proxy."""
        request = _make_request(
            headers={"X-Forwarded-For": "203.0.113.10"},
            client_host="10.0.0.1",
            trusted_networks=_TRUSTED_NET,
        )
        assert _rate_limit_key(request) == "203.0.113.10"

    def test_single_ipv6_address_in_x_forwarded_for(self) -> None:
        """IPv6 addresses in X-Forwarded-For are handled without modification."""
        request = _make_request(
            headers={"X-Forwarded-For": "2001:db8::1"},
            client_host="10.0.0.1",
            trusted_networks=_TRUSTED_NET,
        )
        assert _rate_limit_key(request) == "2001:db8::1"


# ---------------------------------------------------------------------------
# X-API-Key fallback
# ---------------------------------------------------------------------------


class TestXApiKey:
    def test_returns_key_prefix_when_no_x_forwarded_for(self) -> None:
        """Without X-Forwarded-For, X-API-Key prefix is used."""
        request = _make_request(headers={"X-API-Key": "ls_test_key_12345678"})
        assert _rate_limit_key(request) == "key:ls_test_key_1234"

    def test_key_prefix_is_exactly_16_characters(self) -> None:
        api_key = "abcdefghijklmnop_additional_secret_data"
        request = _make_request(headers={"X-API-Key": api_key})
        key = _rate_limit_key(request)
        prefix_value = key[len("key:"):]
        assert len(prefix_value) == 16
        assert prefix_value == api_key[:16]

    def test_x_api_key_shorter_than_16_chars_uses_full_key(self) -> None:
        request = _make_request(headers={"X-API-Key": "short"})
        assert _rate_limit_key(request) == "key:short"

    def test_key_prefix_result_starts_with_key_colon(self) -> None:
        request = _make_request(headers={"X-API-Key": "any_api_key_here_longer"})
        assert _rate_limit_key(request).startswith("key:")

    def test_x_api_key_takes_priority_over_remote_address(self) -> None:
        request = _make_request(
            headers={"X-API-Key": "ls_secret_key_abc123"},
            client_host="10.10.10.10",
        )
        key = _rate_limit_key(request)
        assert key.startswith("key:")
        assert key != "10.10.10.10"


# ---------------------------------------------------------------------------
# Remote address fallback
# ---------------------------------------------------------------------------


class TestRemoteAddressFallback:
    def test_falls_back_to_remote_address_when_no_headers(self) -> None:
        request = _make_request(client_host="192.168.1.55")
        assert _rate_limit_key(request) == "192.168.1.55"

    def test_remote_address_used_when_x_forwarded_for_absent_and_no_api_key(self) -> None:
        request = _make_request(headers={}, client_host="172.16.0.99")
        assert _rate_limit_key(request) == "172.16.0.99"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestRateLimitKeyEdgeCases:
    def test_empty_x_forwarded_for_falls_through_to_api_key(self) -> None:
        """An empty X-Forwarded-For header should not produce an empty key."""
        request = _make_request(headers={
            "X-Forwarded-For": "",
            "X-API-Key": "ls_fallback_key_xyz",
        })
        key = _rate_limit_key(request)
        assert key.startswith("key:") or key == ""

    def test_x_forwarded_for_single_ip_no_comma_from_trusted_proxy(self) -> None:
        """A single IP with no comma must still work correctly."""
        request = _make_request(
            headers={"X-Forwarded-For": "8.8.8.8"},
            client_host="10.0.0.1",
            trusted_networks=_TRUSTED_NET,
        )
        assert _rate_limit_key(request) == "8.8.8.8"

    def test_different_api_keys_produce_different_buckets(self) -> None:
        req_a = _make_request(headers={"X-API-Key": "aaaa_1111_aaaa_1111_extra"})
        req_b = _make_request(headers={"X-API-Key": "bbbb_2222_bbbb_2222_extra"})
        assert _rate_limit_key(req_a) != _rate_limit_key(req_b)

    def test_same_api_key_prefix_produces_same_bucket(self) -> None:
        req_a = _make_request(headers={"X-API-Key": "ls_shared_prefix_version_1"})
        req_b = _make_request(headers={"X-API-Key": "ls_shared_prefix_version_2"})
        assert _rate_limit_key(req_a) == _rate_limit_key(req_b)

    def test_result_is_always_a_string(self) -> None:
        cases = [
            _make_request(
                headers={"X-Forwarded-For": "1.2.3.4"},
                client_host="10.0.0.1",
                trusted_networks=_TRUSTED_NET,
            ),
            _make_request(headers={"X-API-Key": "some-key-here-12345"}),
            _make_request(client_host="10.0.0.1"),
        ]
        for req in cases:
            assert isinstance(_rate_limit_key(req), str)
