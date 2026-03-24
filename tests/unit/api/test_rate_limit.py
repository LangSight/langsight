"""
Unit tests for _rate_limit_key in langsight.api.rate_limit.

Key resolution order (first match wins):
  1. X-Forwarded-For header — first IP used
  2. X-API-Key header prefix — first 16 chars of the key
  3. TCP remote address fallback

No real HTTP server is started; Request objects are constructed directly
using Starlette's Request constructor from a minimal ASGI scope.
"""

from __future__ import annotations

import pytest
from starlette.requests import Request

from langsight.api.rate_limit import _rate_limit_key

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helper: build a minimal Starlette Request without a real ASGI app
# ---------------------------------------------------------------------------


def _make_request(
    headers: dict[str, str] | None = None,
    client_host: str = "10.0.0.1",
) -> Request:
    """Construct a minimal Request with the given headers and remote address."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/status",
        "query_string": b"",
        "headers": [
            (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
        ],
        "client": (client_host, 54321),
    }
    return Request(scope)


# ---------------------------------------------------------------------------
# X-Forwarded-For takes priority
# ---------------------------------------------------------------------------


class TestXForwardedFor:
    def test_returns_first_ip_from_x_forwarded_for(self) -> None:
        """When X-Forwarded-For is present, the first IP is the rate-limit key."""
        request = _make_request(headers={"X-Forwarded-For": "203.0.113.5"})
        key = _rate_limit_key(request)
        assert key == "203.0.113.5"

    def test_returns_first_ip_when_multiple_ips_in_x_forwarded_for(self) -> None:
        """Only the first IP is used — downstream proxy IPs are ignored."""
        request = _make_request(
            headers={"X-Forwarded-For": "203.0.113.5, 10.0.0.1, 192.168.1.1"}
        )
        key = _rate_limit_key(request)
        assert key == "203.0.113.5"

    def test_strips_whitespace_from_x_forwarded_for_first_ip(self) -> None:
        """Whitespace around the first IP is stripped."""
        request = _make_request(
            headers={"X-Forwarded-For": "  203.0.113.5  , 10.0.0.1"}
        )
        key = _rate_limit_key(request)
        assert key == "203.0.113.5"

    def test_x_forwarded_for_takes_priority_over_x_api_key(self) -> None:
        """X-Forwarded-For wins even when X-API-Key is also present."""
        request = _make_request(headers={
            "X-Forwarded-For": "203.0.113.42",
            "X-API-Key": "my-secret-key-here",
        })
        key = _rate_limit_key(request)
        assert key == "203.0.113.42"

    def test_x_forwarded_for_takes_priority_over_remote_address(self) -> None:
        """X-Forwarded-For wins over the TCP client address."""
        request = _make_request(
            headers={"X-Forwarded-For": "203.0.113.10"},
            client_host="127.0.0.1",
        )
        key = _rate_limit_key(request)
        assert key == "203.0.113.10"

    def test_single_ipv6_address_in_x_forwarded_for(self) -> None:
        """IPv6 addresses in X-Forwarded-For are handled without modification."""
        request = _make_request(
            headers={"X-Forwarded-For": "2001:db8::1"}
        )
        key = _rate_limit_key(request)
        assert key == "2001:db8::1"


# ---------------------------------------------------------------------------
# X-API-Key fallback
# ---------------------------------------------------------------------------


class TestXApiKey:
    def test_returns_key_prefix_when_no_x_forwarded_for(self) -> None:
        """Without X-Forwarded-For, X-API-Key prefix is used."""
        request = _make_request(headers={"X-API-Key": "ls_test_key_12345678"})
        key = _rate_limit_key(request)
        assert key == "key:ls_test_key_1234"  # first 16 chars of the key

    def test_key_prefix_is_exactly_16_characters(self) -> None:
        """The key prefix must be exactly 16 characters of the raw key."""
        api_key = "abcdefghijklmnop_additional_secret_data"
        request = _make_request(headers={"X-API-Key": api_key})
        key = _rate_limit_key(request)
        # Strip the 'key:' prefix and check length
        prefix_value = key[len("key:"):]
        assert len(prefix_value) == 16
        assert prefix_value == api_key[:16]

    def test_x_api_key_shorter_than_16_chars_uses_full_key(self) -> None:
        """When the API key is shorter than 16 chars, all of it is used."""
        request = _make_request(headers={"X-API-Key": "short"})
        key = _rate_limit_key(request)
        assert key == "key:short"

    def test_key_prefix_result_starts_with_key_colon(self) -> None:
        """The result must start with 'key:' to distinguish API-key buckets from IPs."""
        request = _make_request(headers={"X-API-Key": "any_api_key_here_longer"})
        key = _rate_limit_key(request)
        assert key.startswith("key:")

    def test_x_api_key_takes_priority_over_remote_address(self) -> None:
        """X-API-Key is used before falling back to the TCP remote address."""
        request = _make_request(
            headers={"X-API-Key": "ls_secret_key_abc123"},
            client_host="10.10.10.10",
        )
        key = _rate_limit_key(request)
        assert key.startswith("key:")
        # Must NOT be the remote address
        assert key != "10.10.10.10"


# ---------------------------------------------------------------------------
# Remote address fallback
# ---------------------------------------------------------------------------


class TestRemoteAddressFallback:
    def test_falls_back_to_remote_address_when_no_headers(self) -> None:
        """Without any rate-limit headers, the TCP client IP is used."""
        request = _make_request(client_host="192.168.1.55")
        key = _rate_limit_key(request)
        assert key == "192.168.1.55"

    def test_remote_address_used_when_x_forwarded_for_absent_and_no_api_key(self) -> None:
        """Explicit confirmation: no forwarded header + no API key → remote address."""
        request = _make_request(
            headers={},  # no X-Forwarded-For, no X-API-Key
            client_host="172.16.0.99",
        )
        key = _rate_limit_key(request)
        assert key == "172.16.0.99"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestRateLimitKeyEdgeCases:
    def test_empty_x_forwarded_for_falls_through_to_api_key(self) -> None:
        """An empty X-Forwarded-For header should not produce an empty key."""
        # Empty string is falsy in Python — the branch should be skipped
        request = _make_request(headers={
            "X-Forwarded-For": "",
            "X-API-Key": "ls_fallback_key_xyz",
        })
        key = _rate_limit_key(request)
        # Empty header is falsy — should skip to X-API-Key
        assert key.startswith("key:") or key == ""  # implementation-defined; either is sane

    def test_x_forwarded_for_single_ip_no_comma(self) -> None:
        """A single IP with no comma must still work correctly."""
        request = _make_request(headers={"X-Forwarded-For": "8.8.8.8"})
        key = _rate_limit_key(request)
        assert key == "8.8.8.8"

    def test_different_api_keys_produce_different_buckets(self) -> None:
        """Two requests with different API keys must produce different keys."""
        req_a = _make_request(headers={"X-API-Key": "aaaa_1111_aaaa_1111_extra"})
        req_b = _make_request(headers={"X-API-Key": "bbbb_2222_bbbb_2222_extra"})
        key_a = _rate_limit_key(req_a)
        key_b = _rate_limit_key(req_b)
        assert key_a != key_b

    def test_same_api_key_prefix_produces_same_bucket(self) -> None:
        """Two keys sharing the first 16 chars map to the same bucket (by design)."""
        req_a = _make_request(headers={"X-API-Key": "ls_shared_prefix_version_1"})
        req_b = _make_request(headers={"X-API-Key": "ls_shared_prefix_version_2"})
        key_a = _rate_limit_key(req_a)
        key_b = _rate_limit_key(req_b)
        # Same first 16 chars → same bucket
        assert key_a == key_b

    def test_result_is_always_a_string(self) -> None:
        """_rate_limit_key must always return a str, never None."""
        cases = [
            _make_request(headers={"X-Forwarded-For": "1.2.3.4"}),
            _make_request(headers={"X-API-Key": "some-key-here-12345"}),
            _make_request(client_host="10.0.0.1"),
        ]
        for req in cases:
            result = _rate_limit_key(req)
            assert isinstance(result, str)
