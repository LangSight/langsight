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
    """A fake LangSightClient whose buffer_span and flush are inspectable."""
    client = MagicMock()
    client.buffer_span = MagicMock()
    client.flush = AsyncMock()
    return client


# ---------------------------------------------------------------------------
# TestSessionStartSpanEmittedAtOpen
# ---------------------------------------------------------------------------


class TestSessionStartSpanEmittedAtOpen:
    """Start span must be emitted at context-manager open, before yield."""

    @pytest.mark.asyncio
    async def test_input_span_flushed_before_yield(self, mock_client) -> None:
        """When input= is passed, buffer_span + flush are called before the body runs."""
        body_ran: list[bool] = []

        with patch("langsight.sdk.auto_patch._global_client", mock_client):
            async with session(agent_name="orchestrator", input="hello") as _sess:
                # If we reach here, buffer_span must already have been called once
                body_ran.append(True)
                calls_at_body_entry = mock_client.buffer_span.call_count

        assert body_ran, "body never ran"
        assert calls_at_body_entry >= 1, "buffer_span not called before yield"

        # Inspect the span passed in that first call
        first_span = mock_client.buffer_span.call_args_list[0][0][0]
        assert first_span.llm_input == "hello"
        assert first_span.llm_output is None
        assert first_span.tool_name == "session"
        mock_client.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_no_start_span_when_no_input(self, mock_client) -> None:
        """When no input= kwarg is supplied, buffer_span is NOT called at open."""
        with patch("langsight.sdk.auto_patch._global_client", mock_client):
            async with session(agent_name="orchestrator") as _sess:
                calls_at_body_entry = mock_client.buffer_span.call_count

        assert calls_at_body_entry == 0, (
            "buffer_span should not be called at open when input= is absent"
        )

    @pytest.mark.asyncio
    async def test_start_span_has_correct_session_id(self, mock_client) -> None:
        """The start span's session_id matches the yielded session context string."""
        with patch("langsight.sdk.auto_patch._global_client", mock_client):
            async with session(agent_name="orchestrator", input="prompt text") as sess:
                yielded_session_id = str(sess)

        first_span = mock_client.buffer_span.call_args_list[0][0][0]
        assert first_span.session_id == yielded_session_id

    @pytest.mark.asyncio
    async def test_start_span_flushed_even_if_agent_crashes(self, mock_client) -> None:
        """Start span is emitted even when the block body raises an exception."""
        with patch("langsight.sdk.auto_patch._global_client", mock_client):
            with pytest.raises(RuntimeError, match="agent exploded"):
                async with session(agent_name="orchestrator", input="crash prompt"):
                    raise RuntimeError("agent exploded")

        # At least one buffer_span call must have the input set
        spans_with_input = [
            c[0][0]
            for c in mock_client.buffer_span.call_args_list
            if c[0][0].llm_input
        ]
        assert len(spans_with_input) >= 1, "No start span was emitted before the crash"
        assert spans_with_input[0].llm_input == "crash prompt"


# ---------------------------------------------------------------------------
# TestSessionCloseSpanBehaviour
# ---------------------------------------------------------------------------


class TestSessionCloseSpanBehaviour:
    """Close-time span rules: emitted iff set_output() was called."""

    @pytest.mark.asyncio
    async def test_close_span_emitted_when_set_output_called(self, mock_client) -> None:
        """set_output() triggers a second span at close carrying both input and output."""
        with patch("langsight.sdk.auto_patch._global_client", mock_client):
            async with session(agent_name="orchestrator", input="prompt") as sess:
                sess.set_output("answer")

        # Expect two buffer_span calls: start span + close span
        assert mock_client.buffer_span.call_count == 2
        close_span = mock_client.buffer_span.call_args_list[1][0][0]
        assert close_span.llm_input == "prompt"
        assert close_span.llm_output == "answer"
        assert close_span.tool_name == "session"

    @pytest.mark.asyncio
    async def test_no_close_span_when_set_output_not_called(self, mock_client) -> None:
        """input= given but set_output() never called → only one buffer_span call."""
        with patch("langsight.sdk.auto_patch._global_client", mock_client):
            async with session(agent_name="orchestrator", input="prompt only") as _sess:
                pass  # set_output() deliberately omitted

        assert mock_client.buffer_span.call_count == 1, (
            "Expected exactly one buffer_span call (start span only)"
        )

    @pytest.mark.asyncio
    async def test_no_spans_emitted_when_no_input_no_output(self, mock_client) -> None:
        """Neither input= nor set_output() → buffer_span never called."""
        with patch("langsight.sdk.auto_patch._global_client", mock_client):
            async with session(agent_name="orchestrator") as _sess:
                pass  # no input, no output

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
