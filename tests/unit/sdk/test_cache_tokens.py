"""Unit tests for Anthropic cache token fields on ToolCallSpan.

Covers:
  - ToolCallSpan stores cache_read_tokens and cache_creation_tokens
  - Both fields default to None when absent
  - _process_anthropic_response() reads cache_read_input_tokens and
    cache_creation_input_tokens from the Anthropic usage object and
    forwards them onto the buffered LLM-generation span.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from langsight.sdk.client import LangSightClient
from langsight.sdk.llm_wrapper import AnthropicProxy, _process_anthropic_response
from langsight.sdk.models import ToolCallSpan, ToolCallStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ls() -> LangSightClient:
    return LangSightClient(url="http://localhost:8000")


def _make_proxy(ls: LangSightClient, agent_name: str = "test-agent") -> AnthropicProxy:
    fake_client = SimpleNamespace()
    fake_client.messages = SimpleNamespace()
    return AnthropicProxy(fake_client, ls, agent_name=agent_name)


def _make_usage(
    input_tokens: int = 100,
    output_tokens: int = 50,
    cache_read_input_tokens: int | None = None,
    cache_creation_input_tokens: int | None = None,
) -> SimpleNamespace:
    """Build a mock Anthropic usage object."""
    usage = SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    # Only set cache attrs when the caller provides a value — mirrors the real
    # Anthropic SDK which omits the attribute entirely when cache is not used.
    if cache_read_input_tokens is not None:
        usage.cache_read_input_tokens = cache_read_input_tokens
    if cache_creation_input_tokens is not None:
        usage.cache_creation_input_tokens = cache_creation_input_tokens
    return usage


def _make_response(
    model: str = "claude-sonnet-4-6",
    usage: SimpleNamespace | None = None,
    content: list | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        model=model,
        usage=usage or _make_usage(),
        content=content or [],
        stop_reason="end_turn",
    )


# ---------------------------------------------------------------------------
# ToolCallSpan field tests
# ---------------------------------------------------------------------------


class TestCacheTokenFields:
    """ToolCallSpan stores and exposes cache token fields correctly."""

    def test_cache_read_tokens_stored(self) -> None:
        """A span created with cache_read_tokens=500 must expose that value."""
        now = datetime.now(UTC)
        span = ToolCallSpan(
            server_name="anthropic",
            tool_name="generate/claude-sonnet-4-6",
            started_at=now,
            ended_at=now,
            status=ToolCallStatus.SUCCESS,
            cache_read_tokens=500,
        )
        assert span.cache_read_tokens == 500

    def test_cache_creation_tokens_stored(self) -> None:
        """A span created with cache_creation_tokens=100 must expose that value."""
        now = datetime.now(UTC)
        span = ToolCallSpan(
            server_name="anthropic",
            tool_name="generate/claude-sonnet-4-6",
            started_at=now,
            ended_at=now,
            status=ToolCallStatus.SUCCESS,
            cache_creation_tokens=100,
        )
        assert span.cache_creation_tokens == 100

    def test_cache_tokens_default_none(self) -> None:
        """Both cache fields default to None when not supplied."""
        now = datetime.now(UTC)
        span = ToolCallSpan(
            server_name="anthropic",
            tool_name="generate/claude-sonnet-4-6",
            started_at=now,
            ended_at=now,
            status=ToolCallStatus.SUCCESS,
        )
        assert span.cache_read_tokens is None
        assert span.cache_creation_tokens is None

    def test_cache_tokens_independent_of_each_other(self) -> None:
        """Setting only one cache field leaves the other as None."""
        now = datetime.now(UTC)

        span_read_only = ToolCallSpan(
            server_name="anthropic",
            tool_name="generate/claude-sonnet-4-6",
            started_at=now,
            ended_at=now,
            status=ToolCallStatus.SUCCESS,
            cache_read_tokens=200,
        )
        assert span_read_only.cache_read_tokens == 200
        assert span_read_only.cache_creation_tokens is None

        span_creation_only = ToolCallSpan(
            server_name="anthropic",
            tool_name="generate/claude-sonnet-4-6",
            started_at=now,
            ended_at=now,
            status=ToolCallStatus.SUCCESS,
            cache_creation_tokens=75,
        )
        assert span_creation_only.cache_creation_tokens == 75
        assert span_creation_only.cache_read_tokens is None

    def test_cache_tokens_survive_json_round_trip(self) -> None:
        """Cache fields are preserved after Pydantic model_dump/model_validate."""
        now = datetime.now(UTC)
        span = ToolCallSpan(
            server_name="anthropic",
            tool_name="generate/claude-sonnet-4-6",
            started_at=now,
            ended_at=now,
            status=ToolCallStatus.SUCCESS,
            cache_read_tokens=300,
            cache_creation_tokens=40,
        )
        data = span.model_dump(mode="json")
        restored = ToolCallSpan.model_validate(data)
        assert restored.cache_read_tokens == 300
        assert restored.cache_creation_tokens == 40

    def test_record_classmethod_forwards_cache_tokens(self) -> None:
        """ToolCallSpan.record() must forward both cache token kwargs."""
        started = datetime.now(UTC)
        span = ToolCallSpan.record(
            server_name="anthropic",
            tool_name="generate/claude-sonnet-4-6",
            started_at=started,
            status=ToolCallStatus.SUCCESS,
            cache_read_tokens=150,
            cache_creation_tokens=30,
        )
        assert span.cache_read_tokens == 150
        assert span.cache_creation_tokens == 30


# ---------------------------------------------------------------------------
# _process_anthropic_response — cache token extraction
# ---------------------------------------------------------------------------


class TestProcessAnthropicResponseCacheTokens:
    """_process_anthropic_response reads cache tokens from usage and sets them on the LLM span."""

    def test_cache_read_tokens_from_anthropic_response(self, ls: LangSightClient) -> None:
        """cache_read_input_tokens=300 on usage → span.cache_read_tokens==300."""
        proxy = _make_proxy(ls)
        usage = _make_usage(
            input_tokens=500,
            output_tokens=120,
            cache_read_input_tokens=300,
        )
        response = _make_response(usage=usage)

        captured: list[ToolCallSpan] = []
        with patch.object(proxy, "_emit_spans", side_effect=lambda s: captured.extend(s)):
            _process_anthropic_response(
                proxy,
                response,
                {"model": "claude-sonnet-4-6", "messages": []},
                datetime.now(UTC),
            )

        assert len(captured) >= 1
        llm_span = captured[0]
        assert llm_span.span_type == "agent"
        assert llm_span.cache_read_tokens == 300
        assert llm_span.cache_creation_tokens is None

    def test_cache_creation_tokens_from_anthropic_response(self, ls: LangSightClient) -> None:
        """cache_creation_input_tokens=50 on usage → span.cache_creation_tokens==50."""
        proxy = _make_proxy(ls)
        usage = _make_usage(
            input_tokens=400,
            output_tokens=80,
            cache_creation_input_tokens=50,
        )
        response = _make_response(usage=usage)

        captured: list[ToolCallSpan] = []
        with patch.object(proxy, "_emit_spans", side_effect=lambda s: captured.extend(s)):
            _process_anthropic_response(
                proxy,
                response,
                {"model": "claude-sonnet-4-6", "messages": []},
                datetime.now(UTC),
            )

        llm_span = captured[0]
        assert llm_span.cache_creation_tokens == 50
        assert llm_span.cache_read_tokens is None

    def test_both_cache_tokens_set_simultaneously(self, ls: LangSightClient) -> None:
        """Both cache fields are read from usage and set on the same span."""
        proxy = _make_proxy(ls)
        usage = _make_usage(
            input_tokens=600,
            output_tokens=200,
            cache_read_input_tokens=300,
            cache_creation_input_tokens=50,
        )
        response = _make_response(usage=usage)

        captured: list[ToolCallSpan] = []
        with patch.object(proxy, "_emit_spans", side_effect=lambda s: captured.extend(s)):
            _process_anthropic_response(
                proxy,
                response,
                {"model": "claude-sonnet-4-6", "messages": []},
                datetime.now(UTC),
            )

        llm_span = captured[0]
        assert llm_span.cache_read_tokens == 300
        assert llm_span.cache_creation_tokens == 50

    def test_cache_tokens_absent_from_usage_become_none(self, ls: LangSightClient) -> None:
        """When the Anthropic usage object has no cache attrs, both fields are None."""
        proxy = _make_proxy(ls)
        # usage has input/output but NO cache attrs
        usage = _make_usage(input_tokens=200, output_tokens=60)
        response = _make_response(usage=usage)

        captured: list[ToolCallSpan] = []
        with patch.object(proxy, "_emit_spans", side_effect=lambda s: captured.extend(s)):
            _process_anthropic_response(
                proxy,
                response,
                {"model": "claude-sonnet-4-6", "messages": []},
                datetime.now(UTC),
            )

        llm_span = captured[0]
        assert llm_span.cache_read_tokens is None
        assert llm_span.cache_creation_tokens is None

    def test_cache_tokens_not_set_on_tool_use_spans(self, ls: LangSightClient) -> None:
        """Cache token fields belong only on the LLM generation span, not tool_use spans."""
        proxy = _make_proxy(ls, agent_name="analyst")
        usage = _make_usage(
            input_tokens=500,
            output_tokens=100,
            cache_read_input_tokens=250,
            cache_creation_input_tokens=40,
        )
        tool_block = SimpleNamespace(type="tool_use", name="search", input={"q": "test"})
        response = _make_response(usage=usage, content=[tool_block])

        captured: list[ToolCallSpan] = []
        with patch.object(proxy, "_emit_spans", side_effect=lambda s: captured.extend(s)):
            _process_anthropic_response(
                proxy,
                response,
                {"model": "claude-sonnet-4-6", "messages": []},
                datetime.now(UTC),
            )

        # First span is the LLM generation span
        llm_span = captured[0]
        assert llm_span.span_type == "agent"
        assert llm_span.cache_read_tokens == 250
        assert llm_span.cache_creation_tokens == 40

        # Second span is the tool intent span — cache fields must be None
        tool_span = captured[1]
        assert tool_span.span_type == "llm_intent"
        assert tool_span.cache_read_tokens is None
        assert tool_span.cache_creation_tokens is None

    def test_regular_tokens_still_present_alongside_cache_tokens(self, ls: LangSightClient) -> None:
        """input_tokens and output_tokens are unaffected when cache tokens are also set."""
        proxy = _make_proxy(ls)
        usage = _make_usage(
            input_tokens=400,
            output_tokens=90,
            cache_read_input_tokens=100,
            cache_creation_input_tokens=25,
        )
        response = _make_response(usage=usage)

        captured: list[ToolCallSpan] = []
        with patch.object(proxy, "_emit_spans", side_effect=lambda s: captured.extend(s)):
            _process_anthropic_response(
                proxy,
                response,
                {"model": "claude-sonnet-4-6", "messages": []},
                datetime.now(UTC),
            )

        llm_span = captured[0]
        assert llm_span.input_tokens == 400
        assert llm_span.output_tokens == 90
        assert llm_span.cache_read_tokens == 100
        assert llm_span.cache_creation_tokens == 25
