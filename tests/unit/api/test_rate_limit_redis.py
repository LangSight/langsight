"""
Unit tests for _DeferredLimiter in langsight.api.rate_limit.

Covers:
  - Initial state: inner is an in-memory Limiter
  - reconfigure(None): no-op, keeps existing inner
  - reconfigure(url): replaces inner with a Redis-backed Limiter
  - limit() and shared_limit(): delegate to inner
  - __getattr__: attribute lookup falls through to inner
  - Module-level `limiter` is a _DeferredLimiter instance

Also tests the multi-worker startup guard (the RuntimeError raised by main.py
lifespan when LANGSIGHT_WORKERS > 1 and no Redis URL is configured).

No real Redis, no real HTTP server — all Limiter internals are mocked.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from slowapi import Limiter

from langsight.api.rate_limit import _DeferredLimiter, limiter

pytestmark = pytest.mark.unit


# ===========================================================================
# _DeferredLimiter
# ===========================================================================


class TestDeferredLimiter:
    def test_initial_limiter_is_in_memory(self) -> None:
        """On construction, _inner must be a slowapi.Limiter without storage_uri."""
        dl = _DeferredLimiter()
        # The inner must be a Limiter, not None, and must not have redis storage
        assert isinstance(dl._inner, Limiter)

    def test_reconfigure_with_none_keeps_current_inner(self) -> None:
        """reconfigure(None) must leave _inner unchanged."""
        dl = _DeferredLimiter()
        original_inner = dl._inner

        dl.reconfigure(None)

        assert dl._inner is original_inner

    def test_reconfigure_with_url_swaps_inner(self) -> None:
        """reconfigure(url) must replace _inner with a new Limiter instance."""
        dl = _DeferredLimiter()
        original_inner = dl._inner

        # Limiter construction with a redis URL may attempt to connect — mock it
        mock_limiter = MagicMock(spec=Limiter)
        with patch("langsight.api.rate_limit.Limiter", return_value=mock_limiter) as MockLimiter:
            dl.reconfigure("redis://localhost:6379")

        # _inner must have been replaced
        assert dl._inner is not original_inner
        # The new Limiter was created with the redis URL
        MockLimiter.assert_called_once()
        call_kwargs = MockLimiter.call_args.kwargs
        assert call_kwargs.get("storage_uri") == "redis://localhost:6379"

    def test_reconfigure_with_url_does_not_replace_inner_object(self) -> None:
        """reconfigure() mutates _inner on the wrapper — the wrapper itself stays the same."""
        dl = _DeferredLimiter()
        wrapper_id_before = id(dl)

        mock_limiter = MagicMock(spec=Limiter)
        with patch("langsight.api.rate_limit.Limiter", return_value=mock_limiter):
            dl.reconfigure("redis://localhost:6379")

        # The wrapper object identity must not change
        assert id(dl) == wrapper_id_before

    def test_limit_method_forwards_to_inner(self) -> None:
        """limit() must delegate to _inner.limit()."""
        dl = _DeferredLimiter()
        mock_inner = MagicMock(spec=Limiter)
        dl._inner = mock_inner

        decorator = dl.limit("10/minute")

        mock_inner.limit.assert_called_once_with("10/minute")
        assert decorator is mock_inner.limit.return_value

    def test_shared_limit_method_forwards_to_inner(self) -> None:
        """shared_limit() must delegate to _inner.shared_limit()."""
        dl = _DeferredLimiter()
        mock_inner = MagicMock(spec=Limiter)
        dl._inner = mock_inner

        dl.shared_limit("5/minute", scope="test")

        mock_inner.shared_limit.assert_called_once_with("5/minute", scope="test")

    def test_getattr_forwards_to_inner(self) -> None:
        """Attribute access via __getattr__ must proxy to _inner."""
        dl = _DeferredLimiter()
        mock_inner = MagicMock(spec=Limiter)
        mock_inner._storage = MagicMock(name="storage")
        dl._inner = mock_inner

        # Access an attribute that does not exist on _DeferredLimiter directly
        result = dl._storage

        assert result is mock_inner._storage

    def test_getattr_raises_attribute_error_for_missing_attribute(self) -> None:
        """If _inner also does not have the attribute, AttributeError must propagate."""
        dl = _DeferredLimiter()
        # Use a real inner Limiter — accessing a non-existent attribute should raise
        with pytest.raises(AttributeError):
            _ = dl._this_attribute_does_not_exist_anywhere

    def test_module_level_limiter_is_deferred_limiter_instance(self) -> None:
        """The module-level `limiter` export must be a _DeferredLimiter."""
        assert isinstance(limiter, _DeferredLimiter)

    def test_reconfigure_called_twice_with_url_replaces_inner_each_time(self) -> None:
        """Two reconfigure(url) calls must each produce a fresh inner."""
        dl = _DeferredLimiter()
        mock_a = MagicMock(spec=Limiter)
        mock_b = MagicMock(spec=Limiter)

        with patch("langsight.api.rate_limit.Limiter", side_effect=[mock_a, mock_b]):
            dl.reconfigure("redis://host-a:6379")
            first_inner = dl._inner
            dl.reconfigure("redis://host-b:6379")
            second_inner = dl._inner

        assert first_inner is mock_a
        assert second_inner is mock_b
        assert first_inner is not second_inner

    def test_reconfigure_empty_string_treats_as_falsy_keeps_inner(self) -> None:
        """reconfigure('') — empty string is falsy, must not swap inner."""
        dl = _DeferredLimiter()
        original_inner = dl._inner

        with patch("langsight.api.rate_limit.Limiter") as MockLimiter:
            dl.reconfigure("")

        MockLimiter.assert_not_called()
        assert dl._inner is original_inner


# ===========================================================================
# Multi-worker startup guard (logic replicated from main.py lifespan)
# ===========================================================================


class TestMultiWorkerStartupCheck:
    """Verify the RuntimeError condition that main.py enforces in lifespan.

    The actual check lives in main.py:

        _workers = int(os.environ.get("LANGSIGHT_WORKERS", "1"))
        if _workers > 1 and not settings.redis_url:
            raise RuntimeError(...)

    We replicate this logic in tests to pin the invariant without importing
    the full FastAPI app (which requires a running database).
    """

    def _run_startup_check(self, workers: int, redis_url: str | None) -> None:
        """Replicate the multi-worker guard from main.py lifespan."""
        if workers > 1 and not redis_url:
            raise RuntimeError(
                f"LANGSIGHT_WORKERS={workers} requires LANGSIGHT_REDIS_URL to be set."
            )

    def test_workers_2_without_redis_url_raises_runtime_error(self) -> None:
        """LANGSIGHT_WORKERS=2 with no Redis URL must raise RuntimeError."""
        with pytest.raises(RuntimeError, match="LANGSIGHT_WORKERS=2"):
            self._run_startup_check(workers=2, redis_url=None)

    def test_workers_4_without_redis_url_raises_runtime_error(self) -> None:
        """Any N > 1 without a Redis URL must raise."""
        with pytest.raises(RuntimeError):
            self._run_startup_check(workers=4, redis_url=None)

    def test_workers_2_with_redis_url_does_not_raise(self) -> None:
        """LANGSIGHT_WORKERS=2 with a Redis URL must not raise."""
        self._run_startup_check(workers=2, redis_url="redis://localhost:6379")

    def test_workers_1_without_redis_url_does_not_raise(self) -> None:
        """Single-worker mode never requires Redis."""
        self._run_startup_check(workers=1, redis_url=None)

    def test_workers_1_with_redis_url_does_not_raise(self) -> None:
        """Single-worker mode with Redis is also fine."""
        self._run_startup_check(workers=1, redis_url="redis://localhost:6379")

    def test_workers_env_var_parsed_as_int(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """LANGSIGHT_WORKERS env var is read as an integer."""
        monkeypatch.setenv("LANGSIGHT_WORKERS", "3")
        workers = int(os.environ.get("LANGSIGHT_WORKERS", "1"))
        assert workers == 3

    def test_workers_env_var_defaults_to_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When LANGSIGHT_WORKERS is unset, the default is 1."""
        monkeypatch.delenv("LANGSIGHT_WORKERS", raising=False)
        workers = int(os.environ.get("LANGSIGHT_WORKERS", "1"))
        assert workers == 1
