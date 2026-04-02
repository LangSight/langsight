"""
Unit tests for langsight.api.redis_client.

Covers:
  - is_redis_configured: all falsy/truthy URL variants
  - get_redis_client: singleton behaviour, ping on first call, safe URL logging
  - close_redis_client: aclose called, _client reset to None, idempotency, no-op when None

All tests work without a real Redis — every redis.asyncio call is mocked.
The module-level _client singleton is reset in a per-test fixture so tests
do not bleed into each other.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import langsight.api.redis_client as rc

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fixture: reset the module-level singleton between every test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_client() -> None:
    """Ensure the singleton starts as None and is cleaned up after each test."""
    rc._client = None
    yield
    rc._client = None


# ===========================================================================
# is_redis_configured
# ===========================================================================


class TestIsRedisConfigured:
    def test_none_returns_false(self) -> None:
        assert rc.is_redis_configured(None) is False

    def test_empty_string_returns_false(self) -> None:
        assert rc.is_redis_configured("") is False

    def test_valid_url_returns_true(self) -> None:
        assert rc.is_redis_configured("redis://localhost:6379") is True

    def test_redis_url_with_password_returns_true(self) -> None:
        assert rc.is_redis_configured("redis://:s3cr3t@redis:6379/0") is True

    def test_redis_sentinel_url_returns_true(self) -> None:
        assert rc.is_redis_configured("redis+sentinel://mymaster:6379") is True


# ===========================================================================
# get_redis_client
# ===========================================================================


class TestGetRedisClient:
    @pytest.mark.asyncio
    async def test_returns_cached_client_on_second_call(self) -> None:
        """When _client is already set, from_url is never called again."""
        fake_client = MagicMock()
        rc._client = fake_client  # pre-seed singleton

        with patch("redis.asyncio.from_url") as mock_from_url:
            result = await rc.get_redis_client("redis://localhost:6379")

        mock_from_url.assert_not_called()
        assert result is fake_client

    @pytest.mark.asyncio
    async def test_ping_called_on_first_connection(self) -> None:
        """On first call, from_url is invoked and ping is awaited."""
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)

        with patch("redis.asyncio.from_url", return_value=mock_client) as mock_from_url:
            result = await rc.get_redis_client("redis://localhost:6379")

        mock_from_url.assert_called_once_with(
            "redis://localhost:6379",
            decode_responses=True,
            max_connections=20,
            socket_connect_timeout=5,
            socket_keepalive=True,
        )
        mock_client.ping.assert_awaited_once()
        assert result is mock_client

    @pytest.mark.asyncio
    async def test_client_stored_as_singleton_after_first_call(self) -> None:
        """After first call, the returned client is stored in _client."""
        mock_client = AsyncMock()

        with patch("redis.asyncio.from_url", return_value=mock_client):
            await rc.get_redis_client("redis://localhost:6379")

        assert rc._client is mock_client

    @pytest.mark.asyncio
    async def test_logs_url_without_credentials(self) -> None:
        """The safe URL logged must strip credentials, keeping only host:port."""
        mock_client = AsyncMock()
        logged_calls: list[dict] = []

        with patch("redis.asyncio.from_url", return_value=mock_client):
            with patch.object(rc.logger, "info", side_effect=lambda *a, **kw: logged_calls.append(kw)):
                await rc.get_redis_client("redis://:s3cr3t@myredis:6379/0")

        assert logged_calls, "Expected logger.info to be called"
        logged_url = logged_calls[0].get("url", "")
        # Credentials must not appear in the logged URL
        assert "s3cr3t" not in logged_url
        # Host portion must appear
        assert "myredis:6379" in logged_url

    @pytest.mark.asyncio
    async def test_logs_plain_url_when_no_credentials(self) -> None:
        """URL without credentials is logged as-is (no '@' stripping needed)."""
        mock_client = AsyncMock()
        logged_calls: list[dict] = []

        with patch("redis.asyncio.from_url", return_value=mock_client):
            with patch.object(rc.logger, "info", side_effect=lambda *a, **kw: logged_calls.append(kw)):
                await rc.get_redis_client("redis://localhost:6379")

        assert logged_calls
        assert "localhost:6379" in logged_calls[0].get("url", "")

    @pytest.mark.asyncio
    async def test_second_call_returns_same_object_identity(self) -> None:
        """Two sequential calls return the exact same object."""
        mock_client = AsyncMock()

        with patch("redis.asyncio.from_url", return_value=mock_client):
            first = await rc.get_redis_client("redis://localhost:6379")
            second = await rc.get_redis_client("redis://localhost:6379")

        assert first is second


# ===========================================================================
# close_redis_client
# ===========================================================================


class TestCloseRedisClient:
    @pytest.mark.asyncio
    async def test_aclose_called_on_existing_client(self) -> None:
        """aclose() must be awaited when a client exists."""
        mock_client = AsyncMock()
        rc._client = mock_client

        await rc.close_redis_client()

        mock_client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_client_set_to_none_after_close(self) -> None:
        """After closing, _client must be reset to None."""
        mock_client = AsyncMock()
        rc._client = mock_client

        await rc.close_redis_client()

        assert rc._client is None

    @pytest.mark.asyncio
    async def test_no_error_when_no_client(self) -> None:
        """close_redis_client() with _client=None must not raise any exception."""
        assert rc._client is None
        await rc.close_redis_client()  # must not raise

    @pytest.mark.asyncio
    async def test_idempotent_second_call_is_no_op(self) -> None:
        """Calling close_redis_client() twice must not raise on the second call."""
        mock_client = AsyncMock()
        rc._client = mock_client

        await rc.close_redis_client()
        await rc.close_redis_client()  # second call — _client is already None

        # aclose was only called once (first close)
        mock_client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_client_remains_none_after_no_op_close(self) -> None:
        """After a no-op close (no client), _client stays None."""
        await rc.close_redis_client()
        assert rc._client is None
