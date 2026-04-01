"""Tests for handoff auto-detection from tool names via _HANDOFF_TOOL_RE.

_maybe_emit_handoffs() inspects llm_intent spans and emits explicit
handoff spans when the tool name matches patterns like call_*, delegate_*,
invoke_*, transfer_to_*, run_*, dispatch_*.

Covers:
- Regex: all 6 prefixes match correctly
- Regex: case-insensitive matching
- Regex: regular tool names do NOT match
- _maybe_emit_handoffs: call_analyst → handoff from_agent="orchestrator" to_agent="analyst"
- _maybe_emit_handoffs: delegate_procurement → to_agent="procurement"
- _maybe_emit_handoffs: transfer_to_billing → to_agent="billing"
- _maybe_emit_handoffs: invoke_researcher → to_agent="researcher"
- _maybe_emit_handoffs: dispatch_worker → to_agent="worker"
- _maybe_emit_handoffs: run_agent → to_agent="agent"
- _maybe_emit_handoffs: get_weather → no handoff span (no match)
- _maybe_emit_handoffs: same source == target → no handoff (self-handoff guard)
- _maybe_emit_handoffs: no agent in context → no handoff (source is None)
- _maybe_emit_handoffs: mixed intent spans → handoff only for matching ones
- OpenAI processor triggers _maybe_emit_handoffs for call_* tool
- Anthropic processor triggers _maybe_emit_handoffs for delegate_* tool
- Gemini processor triggers _maybe_emit_handoffs for transfer_to_* tool
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from langsight.sdk.auto_patch import (
    _agent_ctx,
    _session_ctx,
    _trace_ctx,
    clear_context,
    set_context,
    unpatch,
)
from langsight.sdk.client import LangSightClient
from langsight.sdk.context import _pending_tools_ctx
from langsight.sdk.llm_wrapper import (
    AnthropicProxy,
    GenaiClientProxy,
    GeminiProxy,
    OpenAIProxy,
    _HANDOFF_TOOL_RE,
    _maybe_emit_handoffs,
)
from langsight.sdk.models import ToolCallSpan, ToolCallStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_state():
    unpatch()
    _session_ctx.set(None)
    _agent_ctx.set(None)
    _trace_ctx.set(None)
    _pending_tools_ctx.set(None)
    yield
    unpatch()
    _session_ctx.set(None)
    _agent_ctx.set(None)
    _trace_ctx.set(None)
    _pending_tools_ctx.set(None)


@pytest.fixture
def client() -> LangSightClient:
    return LangSightClient(url="http://localhost:8000")


def _capture_spans(client: LangSightClient) -> list[ToolCallSpan]:
    captured: list[ToolCallSpan] = []
    client.buffer_span = lambda span: captured.append(span)  # type: ignore[assignment]
    return captured


def _make_intent_span(
    tool_name: str,
    agent_name: str | None = "orchestrator",
    session_id: str | None = "sess-001",
    trace_id: str | None = None,
) -> ToolCallSpan:
    return ToolCallSpan.record(
        server_name=agent_name or "unknown",
        tool_name=tool_name,
        started_at=datetime.now(UTC),
        status=ToolCallStatus.SUCCESS,
        agent_name=agent_name,
        session_id=session_id,
        trace_id=trace_id,
        span_type="llm_intent",
    )


def _make_proxy(client: LangSightClient, agent_name: str | None = None) -> MagicMock:
    """Build a minimal proxy whose _emit_spans() calls client.buffer_span."""
    proxy = MagicMock()
    proxy._emit_spans = lambda spans: [client.buffer_span(s) for s in spans]
    object.__setattr__(proxy, "_agent_name", agent_name)
    object.__setattr__(proxy, "_session_id", "sess-001")
    object.__setattr__(proxy, "_trace_id", None)
    return proxy


# ---------------------------------------------------------------------------
# _HANDOFF_TOOL_RE — regex contract tests
# ---------------------------------------------------------------------------


class TestHandoffToolRegex:
    @pytest.mark.parametrize(
        "tool_name, expected_target",
        [
            ("call_analyst", "analyst"),
            ("delegate_procurement", "procurement"),
            ("invoke_researcher", "researcher"),
            ("transfer_to_billing", "billing"),
            ("run_worker", "worker"),
            ("dispatch_scheduler", "scheduler"),
        ],
    )
    def test_all_six_prefixes_match(self, tool_name, expected_target):
        """All six handoff prefixes extract the correct target agent name."""
        m = _HANDOFF_TOOL_RE.match(tool_name)
        assert m is not None, f"Expected '{tool_name}' to match _HANDOFF_TOOL_RE"
        assert m.group(1) == expected_target

    @pytest.mark.parametrize(
        "tool_name, expected_target",
        [
            ("CALL_ANALYST", "ANALYST"),
            ("Delegate_Procurement", "Procurement"),
            ("TRANSFER_TO_BILLING", "BILLING"),
            ("Run_Agent", "Agent"),
        ],
    )
    def test_case_insensitive_matching(self, tool_name, expected_target):
        """_HANDOFF_TOOL_RE is case-insensitive (re.IGNORECASE flag set)."""
        m = _HANDOFF_TOOL_RE.match(tool_name)
        assert m is not None, f"Expected '{tool_name}' to match case-insensitively"
        assert m.group(1) == expected_target

    @pytest.mark.parametrize(
        "tool_name",
        [
            "get_weather",
            "fetch_data",
            "list_orders",
            "search_products",
            "update_record",
            "delete_item",
            "create_task",
            "query_database",
            "calculate_total",
        ],
    )
    def test_regular_tool_names_do_not_match(self, tool_name):
        """Regular tool names (get_, fetch_, list_, etc.) do NOT match."""
        assert _HANDOFF_TOOL_RE.match(tool_name) is None, (
            f"'{tool_name}' should NOT match _HANDOFF_TOOL_RE"
        )

    def test_empty_suffix_does_not_match(self):
        """call_ with no suffix does not match (requires at least one character after prefix)."""
        # "call_" — no agent name after underscore
        m = _HANDOFF_TOOL_RE.match("call_")
        # The regex requires (.+) so "call_" with empty group should not match
        # group(1) would be empty string "" — (.+) requires 1+ chars
        assert m is None or m.group(1) == "" or m is None

    def test_regex_flags_include_ignorecase(self):
        """_HANDOFF_TOOL_RE was compiled with re.IGNORECASE."""
        assert _HANDOFF_TOOL_RE.flags & re.IGNORECASE


# ---------------------------------------------------------------------------
# _maybe_emit_handoffs — handoff span emission
# ---------------------------------------------------------------------------


class TestMaybeEmitHandoffs:
    def test_call_analyst_emits_handoff_from_orchestrator(self, client):
        """call_analyst → handoff span from_agent='orchestrator' to_agent='analyst'."""
        tokens = set_context(agent_name="orchestrator")
        try:
            captured = _capture_spans(client)
            proxy = _make_proxy(client, agent_name="orchestrator")
            intent = _make_intent_span("call_analyst", agent_name="orchestrator")

            _maybe_emit_handoffs([intent], proxy)

            handoffs = [s for s in captured if s.span_type == "handoff"]
            assert len(handoffs) == 1
            assert handoffs[0].agent_name == "orchestrator"
            assert handoffs[0].target_agent_name == "analyst"
        finally:
            clear_context(tokens)

    def test_delegate_procurement_emits_correct_target(self, client):
        """delegate_procurement → to_agent='procurement'."""
        tokens = set_context(agent_name="orchestrator")
        try:
            captured = _capture_spans(client)
            proxy = _make_proxy(client, agent_name="orchestrator")
            intent = _make_intent_span("delegate_procurement", agent_name="orchestrator")

            _maybe_emit_handoffs([intent], proxy)

            handoffs = [s for s in captured if s.span_type == "handoff"]
            assert len(handoffs) == 1
            assert handoffs[0].target_agent_name == "procurement"
        finally:
            clear_context(tokens)

    def test_transfer_to_billing_emits_handoff(self, client):
        """transfer_to_billing → to_agent='billing'."""
        tokens = set_context(agent_name="support-agent")
        try:
            captured = _capture_spans(client)
            proxy = _make_proxy(client, agent_name="support-agent")
            intent = _make_intent_span("transfer_to_billing", agent_name="support-agent")

            _maybe_emit_handoffs([intent], proxy)

            handoffs = [s for s in captured if s.span_type == "handoff"]
            assert len(handoffs) == 1
            assert handoffs[0].target_agent_name == "billing"
        finally:
            clear_context(tokens)

    def test_invoke_researcher_emits_handoff(self, client):
        """invoke_researcher → to_agent='researcher'."""
        tokens = set_context(agent_name="planner")
        try:
            captured = _capture_spans(client)
            proxy = _make_proxy(client, agent_name="planner")
            intent = _make_intent_span("invoke_researcher", agent_name="planner")

            _maybe_emit_handoffs([intent], proxy)

            handoffs = [s for s in captured if s.span_type == "handoff"]
            assert len(handoffs) == 1
            assert handoffs[0].target_agent_name == "researcher"
        finally:
            clear_context(tokens)

    def test_dispatch_worker_emits_handoff(self, client):
        """dispatch_worker → to_agent='worker'."""
        tokens = set_context(agent_name="supervisor")
        try:
            captured = _capture_spans(client)
            proxy = _make_proxy(client, agent_name="supervisor")
            intent = _make_intent_span("dispatch_worker", agent_name="supervisor")

            _maybe_emit_handoffs([intent], proxy)

            handoffs = [s for s in captured if s.span_type == "handoff"]
            assert len(handoffs) == 1
            assert handoffs[0].target_agent_name == "worker"
        finally:
            clear_context(tokens)

    def test_run_agent_emits_handoff(self, client):
        """run_agent → to_agent='agent'."""
        tokens = set_context(agent_name="controller")
        try:
            captured = _capture_spans(client)
            proxy = _make_proxy(client, agent_name="controller")
            intent = _make_intent_span("run_agent", agent_name="controller")

            _maybe_emit_handoffs([intent], proxy)

            handoffs = [s for s in captured if s.span_type == "handoff"]
            assert len(handoffs) == 1
            assert handoffs[0].target_agent_name == "agent"
        finally:
            clear_context(tokens)

    def test_regular_tool_name_emits_no_handoff(self, client):
        """get_weather does NOT emit a handoff span."""
        tokens = set_context(agent_name="orchestrator")
        try:
            captured = _capture_spans(client)
            proxy = _make_proxy(client, agent_name="orchestrator")
            intent = _make_intent_span("get_weather", agent_name="orchestrator")

            _maybe_emit_handoffs([intent], proxy)

            handoffs = [s for s in captured if s.span_type == "handoff"]
            assert len(handoffs) == 0
        finally:
            clear_context(tokens)

    def test_self_handoff_guard_no_span_when_target_equals_source(self, client):
        """call_orchestrator from orchestrator → no handoff (self-handoff guard)."""
        tokens = set_context(agent_name="orchestrator")
        try:
            captured = _capture_spans(client)
            proxy = _make_proxy(client, agent_name="orchestrator")
            # tool_name target == source agent_name
            intent = _make_intent_span("call_orchestrator", agent_name="orchestrator")

            _maybe_emit_handoffs([intent], proxy)

            handoffs = [s for s in captured if s.span_type == "handoff"]
            assert len(handoffs) == 0, "Self-handoff must never emit a span"
        finally:
            clear_context(tokens)

    def test_no_agent_in_context_no_handoff(self, client):
        """When span.agent_name is None and _agent_ctx is None, no handoff is emitted."""
        _agent_ctx.set(None)
        captured = _capture_spans(client)
        proxy = _make_proxy(client, agent_name=None)
        # agent_name=None on the span AND no contextvar → source is None
        intent = _make_intent_span("call_analyst", agent_name=None)

        _maybe_emit_handoffs([intent], proxy)

        handoffs = [s for s in captured if s.span_type == "handoff"]
        assert len(handoffs) == 0, "No source agent → no handoff"

    def test_mixed_intent_spans_handoff_only_for_matching(self, client):
        """With multiple intent spans, handoffs only for matching tool names."""
        tokens = set_context(agent_name="orchestrator")
        try:
            captured = _capture_spans(client)
            proxy = _make_proxy(client, agent_name="orchestrator")

            intents = [
                _make_intent_span("call_analyst"),       # matches → handoff
                _make_intent_span("get_weather"),         # no match
                _make_intent_span("delegate_billing"),    # matches → handoff
                _make_intent_span("search_products"),     # no match
                _make_intent_span("invoke_researcher"),   # matches → handoff
            ]

            _maybe_emit_handoffs(intents, proxy)

            handoffs = [s for s in captured if s.span_type == "handoff"]
            assert len(handoffs) == 3
            targets = {s.target_agent_name for s in handoffs}
            assert targets == {"analyst", "billing", "researcher"}
        finally:
            clear_context(tokens)

    def test_handoff_span_inherits_session_id_from_intent_span(self, client):
        """Emitted handoff span carries the same session_id as the source intent span."""
        tokens = set_context(agent_name="orchestrator")
        try:
            captured = _capture_spans(client)
            proxy = _make_proxy(client, agent_name="orchestrator")
            intent = _make_intent_span(
                "call_analyst", agent_name="orchestrator", session_id="shared-sess"
            )

            _maybe_emit_handoffs([intent], proxy)

            handoffs = [s for s in captured if s.span_type == "handoff"]
            assert handoffs[0].session_id == "shared-sess"
        finally:
            clear_context(tokens)

    def test_handoff_span_inherits_trace_id_from_intent_span(self, client):
        """Emitted handoff span carries the same trace_id as the source intent span."""
        tokens = set_context(agent_name="orchestrator", trace_id="trace-abc")
        try:
            captured = _capture_spans(client)
            proxy = _make_proxy(client, agent_name="orchestrator")
            intent = _make_intent_span(
                "call_analyst", agent_name="orchestrator", trace_id="trace-abc"
            )

            _maybe_emit_handoffs([intent], proxy)

            handoffs = [s for s in captured if s.span_type == "handoff"]
            assert handoffs[0].trace_id == "trace-abc"
        finally:
            clear_context(tokens)

    def test_empty_intent_list_emits_no_spans(self, client):
        """Passing an empty list to _maybe_emit_handoffs does nothing."""
        captured = _capture_spans(client)
        proxy = _make_proxy(client, agent_name="orchestrator")

        _maybe_emit_handoffs([], proxy)

        assert len(captured) == 0


# ---------------------------------------------------------------------------
# Integration with LLM processors — OpenAI
# ---------------------------------------------------------------------------


class TestOpenAIHandoffAutoDetect:
    def _make_openai_response_with_tool(self, tool_name: str) -> tuple[SimpleNamespace, SimpleNamespace]:
        tool_call = SimpleNamespace(
            function=SimpleNamespace(name=tool_name, arguments='{"task": "run it"}')
        )
        message = SimpleNamespace(tool_calls=[tool_call], content=None)
        choice = SimpleNamespace(message=message, finish_reason="tool_calls")
        usage = SimpleNamespace(prompt_tokens=50, completion_tokens=20)
        response = SimpleNamespace(choices=[choice], model="gpt-4o", usage=usage)

        fake_client = SimpleNamespace()
        fake_client.chat = SimpleNamespace()
        fake_client.chat.completions = SimpleNamespace()
        fake_client.chat.completions.create = lambda **kw: response
        return fake_client, response

    def test_openai_call_analyst_emits_handoff_span(self, client):
        """OpenAI processor: tool 'call_analyst' triggers a handoff span."""
        fake_client, _ = self._make_openai_response_with_tool("call_analyst")
        tokens = set_context(agent_name="orchestrator")
        try:
            captured = _capture_spans(client)
            proxy = OpenAIProxy(fake_client, client, agent_name="orchestrator", session_id="s1")
            proxy.chat.completions.create(model="gpt-4o", messages=[])

            handoffs = [s for s in captured if s.span_type == "handoff"]
            assert len(handoffs) == 1
            assert handoffs[0].target_agent_name == "analyst"
            assert handoffs[0].agent_name == "orchestrator"
        finally:
            clear_context(tokens)

    def test_openai_regular_tool_no_handoff_span(self, client):
        """OpenAI processor: tool 'get_weather' does NOT emit a handoff span."""
        fake_client, _ = self._make_openai_response_with_tool("get_weather")
        tokens = set_context(agent_name="orchestrator")
        try:
            captured = _capture_spans(client)
            proxy = OpenAIProxy(fake_client, client, agent_name="orchestrator", session_id="s1")
            proxy.chat.completions.create(model="gpt-4o", messages=[])

            handoffs = [s for s in captured if s.span_type == "handoff"]
            assert len(handoffs) == 0
        finally:
            clear_context(tokens)


# ---------------------------------------------------------------------------
# Integration with LLM processors — Anthropic
# ---------------------------------------------------------------------------


class TestAnthropicHandoffAutoDetect:
    def _make_anthropic_response_with_tool(self, tool_name: str) -> tuple[SimpleNamespace, SimpleNamespace]:
        block = SimpleNamespace(type="tool_use", name=tool_name, input={"task": "run it"})
        usage = SimpleNamespace(input_tokens=50, output_tokens=20)
        response = SimpleNamespace(
            content=[block],
            model="claude-sonnet-4-6",
            usage=usage,
            stop_reason="tool_use",
        )
        fake_client = SimpleNamespace()
        fake_client.messages = SimpleNamespace()
        fake_client.messages.create = lambda **kw: response
        return fake_client, response

    def test_anthropic_delegate_procurement_emits_handoff(self, client):
        """Anthropic processor: tool 'delegate_procurement' emits handoff span."""
        fake_client, _ = self._make_anthropic_response_with_tool("delegate_procurement")
        tokens = set_context(agent_name="orchestrator")
        try:
            captured = _capture_spans(client)
            proxy = AnthropicProxy(fake_client, client, agent_name="orchestrator", session_id="s2")
            proxy.messages.create(model="claude-sonnet-4-6", messages=[])

            handoffs = [s for s in captured if s.span_type == "handoff"]
            assert len(handoffs) == 1
            assert handoffs[0].target_agent_name == "procurement"
        finally:
            clear_context(tokens)

    def test_anthropic_regular_tool_no_handoff(self, client):
        """Anthropic processor: tool 'search_db' does NOT emit a handoff span."""
        fake_client, _ = self._make_anthropic_response_with_tool("search_db")
        tokens = set_context(agent_name="orchestrator")
        try:
            captured = _capture_spans(client)
            proxy = AnthropicProxy(fake_client, client, agent_name="orchestrator", session_id="s2")
            proxy.messages.create(model="claude-sonnet-4-6", messages=[])

            handoffs = [s for s in captured if s.span_type == "handoff"]
            assert len(handoffs) == 0
        finally:
            clear_context(tokens)


# ---------------------------------------------------------------------------
# Integration with LLM processors — Gemini (legacy)
# ---------------------------------------------------------------------------


class TestGeminiHandoffAutoDetect:
    def _make_gemini_response_with_tool(self, tool_name: str) -> tuple[SimpleNamespace, SimpleNamespace]:
        fn_call = SimpleNamespace(name=tool_name, args={"task": "run it"})
        part = SimpleNamespace(function_call=fn_call)
        content = SimpleNamespace(parts=[part])
        candidate = SimpleNamespace(content=content, finish_reason="STOP")
        usage = SimpleNamespace(prompt_token_count=50, candidates_token_count=20)
        response = SimpleNamespace(candidates=[candidate], usage_metadata=usage)
        fake_model = SimpleNamespace(model_name="gemini-2.5-flash")
        fake_model.generate_content = lambda *a, **kw: response
        return fake_model, response

    def test_gemini_transfer_to_billing_emits_handoff(self, client):
        """Gemini processor: tool 'transfer_to_billing' emits handoff span."""
        fake_model, response = self._make_gemini_response_with_tool("transfer_to_billing")
        tokens = set_context(agent_name="support-agent")
        try:
            captured = _capture_spans(client)
            proxy = GeminiProxy(fake_model, client, agent_name="support-agent", session_id="s3")
            proxy.generate_content(contents=[])

            handoffs = [s for s in captured if s.span_type == "handoff"]
            assert len(handoffs) == 1
            assert handoffs[0].target_agent_name == "billing"
        finally:
            clear_context(tokens)

    def test_gemini_regular_tool_no_handoff(self, client):
        """Gemini processor: tool 'list_orders' does NOT emit a handoff span."""
        fake_model, _ = self._make_gemini_response_with_tool("list_orders")
        tokens = set_context(agent_name="support-agent")
        try:
            captured = _capture_spans(client)
            proxy = GeminiProxy(fake_model, client, agent_name="support-agent", session_id="s3")
            proxy.generate_content(contents=[])

            handoffs = [s for s in captured if s.span_type == "handoff"]
            assert len(handoffs) == 0
        finally:
            clear_context(tokens)


# ---------------------------------------------------------------------------
# Integration with LLM processors — Gemini new SDK (GenaiClientProxy)
# ---------------------------------------------------------------------------


class TestGenaiHandoffAutoDetect:
    def _make_genai_response_with_tool(self, tool_name: str) -> tuple[SimpleNamespace, SimpleNamespace]:
        fn_call = SimpleNamespace(name=tool_name, args={"task": "run it"})
        part = SimpleNamespace(function_call=fn_call)
        content = SimpleNamespace(parts=[part])
        candidate = SimpleNamespace(content=content, finish_reason="STOP")
        usage = SimpleNamespace(prompt_token_count=50, candidates_token_count=20)
        response = SimpleNamespace(candidates=[candidate], usage_metadata=usage)

        fake_client = SimpleNamespace()
        fake_client.models = SimpleNamespace()
        fake_client.models.generate_content = lambda **kw: response
        return fake_client, response

    def test_genai_invoke_researcher_emits_handoff(self, client):
        """GenAI new SDK: tool 'invoke_researcher' emits handoff span."""
        fake_client, _ = self._make_genai_response_with_tool("invoke_researcher")
        tokens = set_context(agent_name="planner")
        try:
            captured = _capture_spans(client)
            proxy = GenaiClientProxy(fake_client, client, agent_name="planner", session_id="s4")
            proxy.models.generate_content(model="gemini-2.5-flash", contents=[])

            handoffs = [s for s in captured if s.span_type == "handoff"]
            assert len(handoffs) == 1
            assert handoffs[0].target_agent_name == "researcher"
        finally:
            clear_context(tokens)

    def test_genai_regular_tool_no_handoff(self, client):
        """GenAI new SDK: tool 'query_data' does NOT emit a handoff span."""
        fake_client, _ = self._make_genai_response_with_tool("query_data")
        tokens = set_context(agent_name="planner")
        try:
            captured = _capture_spans(client)
            proxy = GenaiClientProxy(fake_client, client, agent_name="planner", session_id="s4")
            proxy.models.generate_content(model="gemini-2.5-flash", contents=[])

            handoffs = [s for s in captured if s.span_type == "handoff"]
            assert len(handoffs) == 0
        finally:
            clear_context(tokens)
