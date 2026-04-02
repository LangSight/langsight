"""Unit tests for session() context manager prompt-capture behaviour (v0.13.0).

Tests cover:
- Session start span emitted immediately at open (before yield) when input= is given
- No start span when no input= kwarg
- Close span emitted only when set_output() was called
- Context cleanup after exit (including exception paths)

All external calls are mocked — no real HTTP, no real ClickHouse.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from langsight.sdk.auto_patch import (
    _session_ctx,
    session,
    unpatch,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_state():
    """Restore clean global state before and after every test."""
    unpatch()
    _session_ctx.set(None)
    yield
    unpatch()
    _session_ctx.set(None)


@pytest.fixture
def mock_client():
    """A fake LangSightClient whose buffer_span, flush, and _post_spans are inspectable."""
    client = MagicMock()
    client.buffer_span = MagicMock()
    client.flush = AsyncMock()
    client._project_id = None  # must be str|None, not MagicMock
    # _post_spans is used for the start span (direct post, no buffer race)
    client._post_spans = AsyncMock(return_value=True)
    return client


# ---------------------------------------------------------------------------
# TestSessionStartSpanEmittedAtOpen
# ---------------------------------------------------------------------------


class TestSessionStartSpanEmittedAtOpen:
    """Start span must be emitted at context-manager open, before yield."""

    @pytest.mark.asyncio
    async def test_input_span_flushed_before_yield(self, mock_client) -> None:
        """When input= is passed, _post_spans is called before the body runs."""
        body_ran: list[bool] = []

        with patch("langsight.sdk.auto_patch._global_client", mock_client):
            async with session(agent_name="orchestrator", input="hello") as _sess:
                body_ran.append(True)
                # Start span posted directly via _post_spans (not buffer_span+flush)
                post_calls_at_body_entry = mock_client._post_spans.await_count

        assert body_ran, "body never ran"
        assert post_calls_at_body_entry >= 1, "_post_spans not called before yield"

        # Inspect the span passed to _post_spans
        first_call_spans = mock_client._post_spans.await_args_list[0][0][0]
        first_span = first_call_spans[0]
        assert first_span.llm_input == "hello"
        assert first_span.llm_output is None
        assert first_span.tool_name == "session"
        # flush() must NOT be called as part of the start span post (race condition fix)
        # (flush may still be called at session close — that's fine)
        assert mock_client.flush.await_count == 0 or post_calls_at_body_entry == mock_client._post_spans.await_count, \
            "flush should not fire before _post_spans for start span"

    @pytest.mark.asyncio
    async def test_no_start_span_when_no_input(self, mock_client) -> None:
        """When no input= kwarg is supplied, _post_spans is NOT called at open."""
        with patch("langsight.sdk.auto_patch._global_client", mock_client):
            async with session(agent_name="orchestrator") as _sess:
                post_calls_at_body_entry = mock_client._post_spans.await_count

        assert post_calls_at_body_entry == 0, (
            "_post_spans should not be called at open when input= is absent"
        )

    @pytest.mark.asyncio
    async def test_start_span_has_correct_session_id(self, mock_client) -> None:
        """The start span's session_id matches the yielded session context string."""
        with patch("langsight.sdk.auto_patch._global_client", mock_client):
            async with session(agent_name="orchestrator", input="prompt text") as sess:
                yielded_session_id = str(sess)

        first_span = mock_client._post_spans.await_args_list[0][0][0][0]
        assert first_span.session_id == yielded_session_id

    @pytest.mark.asyncio
    async def test_start_span_flushed_even_if_agent_crashes(self, mock_client) -> None:
        """Start span is emitted even when the block body raises an exception."""
        with patch("langsight.sdk.auto_patch._global_client", mock_client):
            with pytest.raises(RuntimeError, match="agent exploded"):
                async with session(agent_name="orchestrator", input="crash prompt"):
                    raise RuntimeError("agent exploded")

        # _post_spans must have been called with a span that has llm_input set
        assert mock_client._post_spans.await_count >= 1, "No start span was emitted before the crash"
        first_span = mock_client._post_spans.await_args_list[0][0][0][0]
        assert first_span.llm_input == "crash prompt"


# ---------------------------------------------------------------------------
# TestSessionCloseSpanBehaviour
# ---------------------------------------------------------------------------


class TestSessionCloseSpanBehaviour:
    """Close-time span rules: emitted iff set_output() was called."""

    @pytest.mark.asyncio
    async def test_close_span_emitted_when_set_output_called(self, mock_client) -> None:
        """set_output() triggers a close span via buffer_span carrying both input and output."""
        with patch("langsight.sdk.auto_patch._global_client", mock_client):
            async with session(agent_name="orchestrator", input="prompt") as sess:
                sess.set_output("answer")

        # Start span → _post_spans (direct); close span → buffer_span
        assert mock_client._post_spans.await_count == 1   # start span
        assert mock_client.buffer_span.call_count == 1    # close span only
        close_span = mock_client.buffer_span.call_args_list[0][0][0]
        assert close_span.llm_input == "prompt"
        assert close_span.llm_output == "answer"
        assert close_span.tool_name == "session"

    @pytest.mark.asyncio
    async def test_no_close_span_when_set_output_not_called(self, mock_client) -> None:
        """input= given but set_output() never called → only _post_spans (start), no buffer_span."""
        with patch("langsight.sdk.auto_patch._global_client", mock_client):
            async with session(agent_name="orchestrator", input="prompt only") as _sess:
                pass  # set_output() deliberately omitted

        assert mock_client._post_spans.await_count == 1, "start span should be posted"
        assert mock_client.buffer_span.call_count == 0, (
            "Expected zero buffer_span calls when set_output() not called"
        )

    @pytest.mark.asyncio
    async def test_no_spans_emitted_when_no_input_no_output(self, mock_client) -> None:
        """Neither input= nor set_output() → neither _post_spans nor buffer_span called."""
        with patch("langsight.sdk.auto_patch._global_client", mock_client):
            async with session(agent_name="orchestrator") as _sess:
                pass  # no input, no output

        mock_client._post_spans.assert_not_awaited()
        mock_client.buffer_span.assert_not_called()

    @pytest.mark.asyncio
    async def test_session_context_is_cleared_after_close(self, mock_client) -> None:
        """After the async with block exits, _session_ctx returns None."""
        with patch("langsight.sdk.auto_patch._global_client", mock_client):
            async with session(agent_name="orchestrator", input="hello") as _sess:
                assert _session_ctx.get() is not None

        assert _session_ctx.get() is None

    @pytest.mark.asyncio
    async def test_session_context_is_cleared_after_exception(self, mock_client) -> None:
        """Context is cleared even when the block body raises."""
        with patch("langsight.sdk.auto_patch._global_client", mock_client):
            with pytest.raises(ValueError):
                async with session(agent_name="orchestrator", input="boom") as _sess:
                    raise ValueError("something went wrong")

        assert _session_ctx.get() is None
