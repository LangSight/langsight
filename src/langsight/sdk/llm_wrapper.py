"""
LLM client wrappers — auto-trace tool calls from raw SDK responses.

Wraps OpenAI, Anthropic, and Gemini SDK clients to automatically capture:
- LLM generation spans (model, tokens, cost)
- Tool use blocks from the response as tool_call spans
- Input prompt + output text

Usage::

    from langsight.sdk import LangSightClient

    ls = LangSightClient(url="http://localhost:8000", project_id="...")

    # OpenAI
    from openai import OpenAI
    client = ls.wrap_llm(OpenAI(), agent_name="my-agent")

    # Anthropic
    from anthropic import Anthropic
    client = ls.wrap_llm(Anthropic(), agent_name="my-agent")

    # Gemini (new google.genai SDK)
    from google import genai
    client = ls.wrap_llm(genai.Client(), agent_name="analyst")
    response = await client.aio.models.generate_content(model="gemini-2.5-flash", ...)

    # Gemini (legacy google.generativeai SDK)
    import google.generativeai as genai
    model = ls.wrap_llm(genai.GenerativeModel("gemini-2.5-flash"), agent_name="analyst")

The wrapper is transparent — all attributes and methods forward to the
original client. Only the main generation method is intercepted.

Does NOT import any LLM SDK at module level. Detection is lazy.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime
from typing import Any

import structlog

from langsight.sdk.context import register_pending_tool
from langsight.sdk.models import ToolCallSpan, ToolCallStatus

# ---------------------------------------------------------------------------
# Handoff auto-detection
# ---------------------------------------------------------------------------

# Tool names matching these patterns signal agent delegation (v0.12.0).
# The captured group becomes the target agent name.
#
# Examples:
#   call_analyst       → handoff to "analyst"
#   delegate_billing   → handoff to "billing"
#   invoke_researcher  → handoff to "researcher"
#   transfer_to_ops    → handoff to "ops"
#   run_summarizer     → handoff to "summarizer"
#   dispatch_validator → handoff to "validator"
#
# The pattern is intentionally broad — any verb prefix followed by an
# underscore separator is sufficient to trigger handoff detection. False
# positives (e.g. "run_sql" is not a handoff) are suppressed by the
# source == target guard in _maybe_emit_handoffs.
_HANDOFF_TOOL_RE = re.compile(
    r"^(?:call|delegate|invoke|transfer_to|run|dispatch)_(.+)$",
    re.IGNORECASE,
)


def _maybe_emit_handoffs(
    intent_spans: list[ToolCallSpan],
    proxy: Any,
) -> None:
    """Emit explicit handoff spans for tool calls that signal agent delegation.

    v0.12.0 auto-detection: when the LLM selects a tool whose name matches
    ``_HANDOFF_TOOL_RE`` (``call_*``, ``delegate_*``, ``invoke_*``,
    ``transfer_to_*``, ``run_*``, ``dispatch_*``), LangSight automatically
    emits a handoff span from the current agent to the target. No
    ``create_handoff()`` call is required.

    This produces a solid edge in the session topology graph instead of a
    timing-inferred dashed edge. The ``gemini-sdk-ai-e2e`` pattern of
    ``call_analyst`` / ``call_procurement`` tools is the primary use case —
    these tool names now produce explicit lineage without any code change.

    The source agent is resolved from (in order):
    1. ``span.agent_name`` on the intent span
    2. ``_agent_ctx`` contextvar (set by ``session()`` or ``set_context()``)

    Self-handoffs (target == source) are suppressed. Spans with no resolved
    source agent are silently skipped.

    Called after intent spans are registered — so the handoff span appears
    in the correct position in the timeline and can be claimed by downstream
    spans as a parent.
    """
    from langsight.sdk.auto_patch import _agent_ctx, _session_ctx, _trace_ctx

    for span in intent_spans:
        m = _HANDOFF_TOOL_RE.match(span.tool_name)
        if not m:
            continue

        target_agent = m.group(1)
        source_agent = span.agent_name or _agent_ctx.get() or None

        # Only emit if target differs from source — avoid self-handoffs
        if not source_agent or target_agent == source_agent:
            continue

        handoff = ToolCallSpan.handoff_span(
            from_agent=source_agent,
            to_agent=target_agent,
            started_at=span.started_at,
            trace_id=span.trace_id or _trace_ctx.get() or None,
            session_id=span.session_id or _session_ctx.get() or None,
            parent_span_id=span.parent_span_id,
            project_id=getattr(span, "project_id", None) or None,
        )
        proxy._emit_spans([handoff])


# finish_reason values treated as errors across all LLM SDKs
_FINISH_REASON_ERRORS = frozenset(
    {
        # OpenAI / Google GenAI
        "content_filter",
        "SAFETY",
        "RECITATION",
        "PROHIBITED_CONTENT",
        # Anthropic
        "content_filtered",
    }
)
# finish_reason values that indicate truncation (warn but not error)
_FINISH_REASON_TRUNCATED = frozenset({"length", "MAX_TOKENS", "max_tokens"})


def _extract_finish_reason(response: Any, sdk: str) -> str | None:
    """Return the raw finish_reason string from an LLM response, normalised to lowercase."""
    try:
        if sdk == "openai":
            choices = getattr(response, "choices", None) or []
            if choices:
                fr = getattr(choices[0], "finish_reason", None)
                return str(fr).lower() if fr is not None else None
        elif sdk == "anthropic":
            fr = getattr(response, "stop_reason", None)
            return str(fr).lower() if fr is not None else None
        elif sdk == "gemini":
            candidates = getattr(response, "candidates", None) or []
            if candidates:
                fr = getattr(candidates[0], "finish_reason", None)
                name = getattr(fr, "name", str(fr) if fr is not None else None)
                return str(name).lower() if name is not None else None
    except Exception:  # noqa: BLE001
        pass
    return None


def _check_finish_reason(
    response: Any,
    status: ToolCallStatus,
    error: str | None,
    *,
    sdk: str,
) -> tuple[ToolCallStatus, str | None]:
    """Inspect finish_reason and empty choices/candidates after a successful LLM call.

    Returns (status, error) — may override SUCCESS with ERROR/TIMEOUT.
    """
    if status != ToolCallStatus.SUCCESS or response is None:
        return status, error  # already failed — don't override

    if sdk == "openai":
        choices = getattr(response, "choices", None) or []
        if not choices:
            return (
                ToolCallStatus.ERROR,
                "EmptyResponse: no choices returned (possible content filter)",
            )
        finish = getattr(choices[0], "finish_reason", None)
        if finish in _FINISH_REASON_ERRORS:
            return ToolCallStatus.ERROR, f"ContentFilter: finish_reason={finish}"
        if finish in _FINISH_REASON_TRUNCATED:
            return ToolCallStatus.ERROR, f"Truncated: finish_reason={finish} (output cut off)"

    elif sdk == "anthropic":
        stop_reason = getattr(response, "stop_reason", None)
        if stop_reason == "content_filtered":
            return ToolCallStatus.ERROR, "ContentFilter: response was content-filtered"

    elif sdk == "gemini":
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return (
                ToolCallStatus.ERROR,
                "EmptyResponse: no candidates returned (possible safety filter)",
            )
        # Check first candidate finish reason
        first = candidates[0]
        finish = getattr(first, "finish_reason", None)
        # Gemini finish_reason is an enum — check name or value
        finish_name = getattr(finish, "name", str(finish) if finish is not None else None)
        if finish_name in _FINISH_REASON_ERRORS:
            return ToolCallStatus.ERROR, f"ContentFilter: finish_reason={finish_name}"
        if finish_name in _FINISH_REASON_TRUNCATED:
            return ToolCallStatus.ERROR, f"Truncated: finish_reason={finish_name} (output cut off)"

    return status, error


logger = structlog.get_logger()


class _LLMProxyBase:
    """Base proxy that forwards all attribute access to the wrapped client."""

    def __init__(
        self,
        client: Any,
        langsight: Any,  # LangSightClient — avoid circular import
        agent_name: str | None = None,
        session_id: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        object.__setattr__(self, "_client", client)
        object.__setattr__(self, "_langsight", langsight)
        object.__setattr__(self, "_agent_name", agent_name)
        object.__setattr__(self, "_session_id", session_id)
        object.__setattr__(self, "_trace_id", trace_id)
        object.__setattr__(self, "_redact", getattr(langsight, "_redact_payloads", False))
        object.__setattr__(self, "_project_id", getattr(langsight, "_project_id", None) or "")

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to the wrapped LLM client."""
        return getattr(object.__getattribute__(self, "_client"), name)

    def _emit_spans(self, spans: list[ToolCallSpan]) -> None:
        """Buffer spans synchronously. Thread-safe, no event loop needed."""
        langsight = object.__getattribute__(self, "_langsight")
        for span in spans:
            langsight.buffer_span(span)


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------


class OpenAIProxy(_LLMProxyBase):
    """Wraps an OpenAI client to auto-trace LLM calls and tool use blocks.

    Intercepts ``client.chat.completions.create()`` — both sync and async.
    """

    @property
    def chat(self) -> _OpenAIChatProxy:
        return _OpenAIChatProxy(self)


class _OpenAIChatProxy:
    """Proxy for ``client.chat`` that returns a completions proxy."""

    def __init__(self, parent: OpenAIProxy) -> None:
        self._parent = parent

    @property
    def completions(self) -> _OpenAICompletionsProxy:
        """Return the completions proxy with instrumented create()."""
        return _OpenAICompletionsProxy(self._parent)


class _OpenAICompletionsProxy:
    """Proxy for ``client.chat.completions`` that intercepts create()."""

    def __init__(self, parent: OpenAIProxy) -> None:
        self._parent = parent

    def create(self, **kwargs: Any) -> Any:
        """Intercept sync chat.completions.create()."""
        client = object.__getattribute__(self._parent, "_client")
        started_at = datetime.now(UTC)
        status = ToolCallStatus.SUCCESS
        error: str | None = None
        response: Any = None
        try:
            response = client.chat.completions.create(**kwargs)
            return response
        except TimeoutError as exc:
            status = ToolCallStatus.TIMEOUT
            error = f"{type(exc).__name__}: {exc}"
            raise
        except asyncio.CancelledError as exc:
            status = ToolCallStatus.TIMEOUT
            error = f"CancelledError: {exc or 'request cancelled'}"
            raise
        except BaseException as exc:  # noqa: BLE001
            status = ToolCallStatus.ERROR
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            _process_openai_response(
                self._parent, response, kwargs, started_at, status=status, error=error
            )

    async def acreate(self, **kwargs: Any) -> Any:
        """Intercept async chat.completions.create()."""
        client = object.__getattribute__(self._parent, "_client")
        started_at = datetime.now(UTC)
        status = ToolCallStatus.SUCCESS
        error: str | None = None
        response: Any = None
        try:
            response = await client.chat.completions.create(**kwargs)
            return response
        except TimeoutError as exc:
            status = ToolCallStatus.TIMEOUT
            error = f"{type(exc).__name__}: {exc}"
            raise
        except asyncio.CancelledError as exc:
            status = ToolCallStatus.TIMEOUT
            error = f"CancelledError: {exc or 'request cancelled'}"
            raise
        except BaseException as exc:  # noqa: BLE001
            status = ToolCallStatus.ERROR
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            _process_openai_response(
                self._parent, response, kwargs, started_at, status=status, error=error
            )


def _process_openai_response(
    proxy: Any,  # OpenAIProxy at runtime; Any to accept _AutoPatchProxy from auto_patch
    response: Any,
    kwargs: dict[str, Any],
    started_at: datetime,
    status: ToolCallStatus = ToolCallStatus.SUCCESS,
    error: str | None = None,
) -> None:
    """Extract tool calls and token usage from an OpenAI response."""
    agent_name = object.__getattribute__(proxy, "_agent_name")
    session_id = object.__getattribute__(proxy, "_session_id")
    trace_id = object.__getattribute__(proxy, "_trace_id")
    project_id = object.__getattribute__(proxy, "_project_id")
    redact = object.__getattribute__(proxy, "_redact")

    model = (
        getattr(response, "model", kwargs.get("model", "unknown"))
        if response is not None
        else kwargs.get("model", "unknown")
    )
    usage = getattr(response, "usage", None) if response is not None else None
    input_tokens = getattr(usage, "prompt_tokens", None) if usage else None
    output_tokens = getattr(usage, "completion_tokens", None) if usage else None

    spans: list[ToolCallSpan] = []

    # Inspect finish_reason / empty choices for silent failures
    status, error = _check_finish_reason(response, status, error, sdk="openai")
    finish_reason = _extract_finish_reason(response, sdk="openai")

    # Extract prompt (llm_input) and completion (llm_output) unless redacted
    llm_input: str | None = None
    llm_output: str | None = None
    if not redact:
        messages = kwargs.get("messages")
        if messages:
            user_msgs = [m for m in messages if isinstance(m, dict) and m.get("role") == "user"]
            if user_msgs:
                content = user_msgs[-1].get("content", "")
                llm_input = str(content)[:4000] if content else None

        if response is not None:
            choices = getattr(response, "choices", []) or []
            if choices:
                msg = getattr(choices[0], "message", None)
                if msg:
                    llm_output = str(getattr(msg, "content", "") or "")[:4000]

    # LLM generation span
    llm_span = ToolCallSpan.record(
        server_name="openai",
        tool_name=f"generate/{model}",
        started_at=started_at,
        status=status,
        error=error,
        agent_name=agent_name,
        session_id=session_id,
        trace_id=trace_id,
        span_type="agent",
        project_id=project_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model_id=model,
        finish_reason=finish_reason,
        llm_input=llm_input,
        llm_output=llm_output,
    )
    spans.append(llm_span)

    # Tool use spans from the response — only on success
    choices = (
        getattr(response, "choices", [])
        if response is not None and status == ToolCallStatus.SUCCESS
        else []
    )
    if choices:
        message = getattr(choices[0], "message", None)
        tool_calls = getattr(message, "tool_calls", None) or []
        for tc in tool_calls:
            fn = getattr(tc, "function", None)
            if not fn:
                continue
            tool_name = getattr(fn, "name", "unknown")
            args_str = getattr(fn, "arguments", "")
            try:
                input_args = json.loads(args_str) if args_str and not redact else None
            except (json.JSONDecodeError, TypeError):
                input_args = {"raw": args_str} if not redact else None

            tool_span = ToolCallSpan.record(
                server_name=agent_name or "openai",
                tool_name=tool_name,
                started_at=started_at,
                status=ToolCallStatus.SUCCESS,
                agent_name=agent_name,
                session_id=session_id,
                trace_id=trace_id,
                parent_span_id=llm_span.span_id,
                span_type="llm_intent",
                project_id=project_id,
                input_args=input_args,
            )
            spans.append(tool_span)

    if spans:
        proxy._emit_spans(spans)
        intent_spans = []
        # Register llm_intent spans so wrap() can claim them as parents
        for s in spans:
            if s.span_type == "llm_intent":
                register_pending_tool(s.tool_name, s.span_id, s.agent_name)
                intent_spans.append(s)
        # Auto-emit handoff spans for call_*/delegate_* tool patterns
        _maybe_emit_handoffs(intent_spans, proxy)
        logger.debug(
            "llm_wrapper.openai_traced",
            model=model,
            tool_calls=len(spans) - 1,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------


class AnthropicProxy(_LLMProxyBase):
    """Wraps an Anthropic client to auto-trace LLM calls and tool_use blocks.

    Intercepts ``client.messages.create()`` — both sync and async.
    """

    @property
    def messages(self) -> _AnthropicMessagesProxy:
        return _AnthropicMessagesProxy(self)


class _AnthropicMessagesProxy:
    """Proxy for ``client.messages`` that intercepts create()."""

    def __init__(self, parent: AnthropicProxy) -> None:
        self._parent = parent

    def create(self, **kwargs: Any) -> Any:
        """Intercept sync messages.create()."""
        client = object.__getattribute__(self._parent, "_client")
        started_at = datetime.now(UTC)
        status = ToolCallStatus.SUCCESS
        error: str | None = None
        response: Any = None
        try:
            response = client.messages.create(**kwargs)
            return response
        except TimeoutError as exc:
            status = ToolCallStatus.TIMEOUT
            error = f"{type(exc).__name__}: {exc}"
            raise
        except asyncio.CancelledError as exc:
            status = ToolCallStatus.TIMEOUT
            error = f"CancelledError: {exc or 'request cancelled'}"
            raise
        except BaseException as exc:  # noqa: BLE001
            status = ToolCallStatus.ERROR
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            _process_anthropic_response(
                self._parent, response, kwargs, started_at, status=status, error=error
            )

    async def acreate(self, **kwargs: Any) -> Any:
        """Intercept async messages.create()."""
        client = object.__getattribute__(self._parent, "_client")
        started_at = datetime.now(UTC)
        status = ToolCallStatus.SUCCESS
        error: str | None = None
        response: Any = None
        try:
            response = await client.messages.create(**kwargs)
            return response
        except TimeoutError as exc:
            status = ToolCallStatus.TIMEOUT
            error = f"{type(exc).__name__}: {exc}"
            raise
        except asyncio.CancelledError as exc:
            status = ToolCallStatus.TIMEOUT
            error = f"CancelledError: {exc or 'request cancelled'}"
            raise
        except BaseException as exc:  # noqa: BLE001
            status = ToolCallStatus.ERROR
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            _process_anthropic_response(
                self._parent, response, kwargs, started_at, status=status, error=error
            )


def _process_anthropic_response(
    proxy: Any,  # AnthropicProxy at runtime; Any to accept _AutoPatchProxy from auto_patch
    response: Any,
    kwargs: dict[str, Any],
    started_at: datetime,
    status: ToolCallStatus = ToolCallStatus.SUCCESS,
    error: str | None = None,
) -> None:
    """Extract tool_use blocks and token usage from an Anthropic response."""
    agent_name = object.__getattribute__(proxy, "_agent_name")
    session_id = object.__getattribute__(proxy, "_session_id")
    trace_id = object.__getattribute__(proxy, "_trace_id")
    project_id = object.__getattribute__(proxy, "_project_id")
    redact = object.__getattribute__(proxy, "_redact")

    model = (
        getattr(response, "model", kwargs.get("model", "unknown"))
        if response is not None
        else kwargs.get("model", "unknown")
    )
    usage = getattr(response, "usage", None) if response is not None else None
    input_tokens = getattr(usage, "input_tokens", None) if usage else None
    output_tokens = getattr(usage, "output_tokens", None) if usage else None
    # Anthropic prompt caching — gen_ai.usage.cache_read_input_tokens /
    # gen_ai.usage.cache_creation_input_tokens (OTel GenAI spec)
    cache_read_tokens = getattr(usage, "cache_read_input_tokens", None) if usage else None
    cache_creation_tokens = getattr(usage, "cache_creation_input_tokens", None) if usage else None

    spans: list[ToolCallSpan] = []

    # Inspect stop_reason for silent failures (content_filtered)
    status, error = _check_finish_reason(response, status, error, sdk="anthropic")
    finish_reason = _extract_finish_reason(response, sdk="anthropic")

    # Extract prompt (llm_input) and completion (llm_output) unless redacted
    llm_input: str | None = None
    llm_output: str | None = None
    if not redact:
        # Prompt — extract from kwargs["messages"] (Anthropic format)
        messages = kwargs.get("messages")
        if messages:
            # Take last user/human message for brevity
            user_msgs = [
                m for m in messages if isinstance(m, dict) and m.get("role") in ("user", "human")
            ]
            if user_msgs:
                content = user_msgs[-1].get("content", "")
                if isinstance(content, list):
                    # Multi-modal: extract text blocks
                    text_parts = [
                        b.get("text", "")
                        for b in content
                        if isinstance(b, dict) and b.get("type") == "text"
                    ]
                    llm_input = "\n".join(text_parts) if text_parts else str(content)
                else:
                    llm_input = str(content) if content else None
            if llm_input:
                llm_input = llm_input[:4000]

        # Completion — extract text from response content blocks
        if response is not None:
            resp_content = getattr(response, "content", None) or []
            text_parts = []
            for block in resp_content:
                if getattr(block, "type", None) == "text":
                    text_parts.append(getattr(block, "text", ""))
            if text_parts:
                llm_output = "\n".join(text_parts)[:4000]

    # LLM generation span
    llm_span = ToolCallSpan.record(
        server_name="anthropic",
        tool_name=f"generate/{model}",
        started_at=started_at,
        status=status,
        error=error,
        agent_name=agent_name,
        session_id=session_id,
        trace_id=trace_id,
        span_type="agent",
        project_id=project_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model_id=model,
        finish_reason=finish_reason,
        cache_read_tokens=cache_read_tokens,
        cache_creation_tokens=cache_creation_tokens,
        llm_input=llm_input,
        llm_output=llm_output,
    )
    spans.append(llm_span)

    # Tool use spans from content blocks — only on success
    content = (
        (getattr(response, "content", []) or [])
        if response is not None and status == ToolCallStatus.SUCCESS
        else []
    )
    for block in content:
        if getattr(block, "type", None) != "tool_use":
            continue
        tool_name = getattr(block, "name", "unknown")
        input_args = getattr(block, "input", None) if not redact else None

        tool_span = ToolCallSpan.record(
            server_name=agent_name or "anthropic",
            tool_name=tool_name,
            started_at=started_at,
            status=ToolCallStatus.SUCCESS,
            agent_name=agent_name,
            session_id=session_id,
            trace_id=trace_id,
            parent_span_id=llm_span.span_id,
            span_type="llm_intent",
            project_id=project_id,
            input_args=input_args if isinstance(input_args, dict) else None,
        )
        spans.append(tool_span)

    if spans:
        proxy._emit_spans(spans)
        intent_spans = []
        for s in spans:
            if s.span_type == "llm_intent":
                register_pending_tool(s.tool_name, s.span_id, s.agent_name)
                intent_spans.append(s)
        _maybe_emit_handoffs(intent_spans, proxy)
        logger.debug(
            "llm_wrapper.anthropic_traced",
            model=model,
            tool_calls=len(spans) - 1,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------


class GeminiProxy(_LLMProxyBase):
    """Wraps a Gemini GenerativeModel to auto-trace LLM calls and function calls.

    Intercepts ``model.generate_content()`` and ``model.generate_content_async()``.
    """

    def generate_content(self, *args: Any, **kwargs: Any) -> Any:
        """Intercept sync generate_content()."""
        client = object.__getattribute__(self, "_client")
        started_at = datetime.now(UTC)
        status = ToolCallStatus.SUCCESS
        error: str | None = None
        response: Any = None
        try:
            response = client.generate_content(*args, **kwargs)
            return response
        except TimeoutError as exc:
            status = ToolCallStatus.TIMEOUT
            error = f"{type(exc).__name__}: {exc}"
            raise
        except asyncio.CancelledError as exc:
            status = ToolCallStatus.TIMEOUT
            error = f"CancelledError: {exc or 'request cancelled'}"
            raise
        except BaseException as exc:  # noqa: BLE001
            status = ToolCallStatus.ERROR
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            _process_gemini_response(self, response, kwargs, started_at, status=status, error=error)

    async def generate_content_async(self, *args: Any, **kwargs: Any) -> Any:
        """Intercept async generate_content_async()."""
        client = object.__getattribute__(self, "_client")
        started_at = datetime.now(UTC)
        status = ToolCallStatus.SUCCESS
        error: str | None = None
        response: Any = None
        try:
            response = await client.generate_content_async(*args, **kwargs)
            return response
        except TimeoutError as exc:
            status = ToolCallStatus.TIMEOUT
            error = f"{type(exc).__name__}: {exc}"
            raise
        except asyncio.CancelledError as exc:
            status = ToolCallStatus.TIMEOUT
            error = f"CancelledError: {exc or 'request cancelled'}"
            raise
        except BaseException as exc:  # noqa: BLE001
            status = ToolCallStatus.ERROR
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            _process_gemini_response(self, response, kwargs, started_at, status=status, error=error)


def _process_gemini_response(
    proxy: Any,  # _LLMProxyBase at runtime; Any to accept _AutoPatchProxy from auto_patch
    response: Any,
    kwargs: dict[str, Any],
    started_at: datetime,
    model_override: str | None = None,
    status: ToolCallStatus = ToolCallStatus.SUCCESS,
    error: str | None = None,
) -> None:
    """Extract function calls and token usage from a Gemini response.

    Shared by both GeminiProxy (old SDK) and GenaiClientProxy (new SDK).
    When ``model_override`` is set (new SDK), it is used directly.
    Otherwise the model name is extracted from the wrapped client object.
    """
    agent_name = object.__getattribute__(proxy, "_agent_name")
    session_id = object.__getattribute__(proxy, "_session_id")
    trace_id = object.__getattribute__(proxy, "_trace_id")
    project_id = object.__getattribute__(proxy, "_project_id")
    redact = object.__getattribute__(proxy, "_redact")

    if model_override:
        model = model_override
    else:
        # Legacy SDK — model name stored on the GenerativeModel object
        client = object.__getattribute__(proxy, "_client")
        model = str(getattr(client, "model_name", None) or getattr(client, "_model_name", "gemini"))

    # Token usage from usage_metadata — only available on success
    usage = getattr(response, "usage_metadata", None) if response is not None else None
    input_tokens = getattr(usage, "prompt_token_count", None) if usage else None
    output_tokens = getattr(usage, "candidates_token_count", None) if usage else None

    spans: list[ToolCallSpan] = []

    # Inspect finish_reason / empty candidates for silent failures (safety filter)
    status, error = _check_finish_reason(response, status, error, sdk="gemini")
    finish_reason = _extract_finish_reason(response, sdk="gemini")

    # Extract prompt (llm_input) and completion (llm_output) unless redacted
    llm_input: str | None = None
    llm_output: str | None = None
    if not redact:
        # Gemini: kwargs may have "contents" (list of Content objects or dicts)
        contents = kwargs.get("contents")
        if contents:
            if isinstance(contents, str):
                llm_input = contents[:4000]
            elif isinstance(contents, list) and contents:
                last = contents[-1]
                if isinstance(last, str):
                    llm_input = last[:4000]
                elif isinstance(last, dict):
                    llm_input = str(last.get("parts", last))[:4000]
                else:
                    # Content object
                    llm_input = str(getattr(last, "parts", last))[:4000]

        if response is not None:
            text = getattr(response, "text", None)
            if text:
                llm_output = str(text)[:4000]

    # LLM generation span
    llm_span = ToolCallSpan.record(
        server_name="gemini",
        tool_name=f"generate/{model}",
        started_at=started_at,
        status=status,
        error=error,
        agent_name=agent_name,
        session_id=session_id,
        trace_id=trace_id,
        span_type="agent",
        project_id=project_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model_id=model,
        finish_reason=finish_reason,
        llm_input=llm_input,
        llm_output=llm_output,
    )
    spans.append(llm_span)

    # Function call spans from response parts — only on success
    try:
        candidates = (
            (getattr(response, "candidates", []) or [])
            if response is not None and status == ToolCallStatus.SUCCESS
            else []
        )
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", []) if content else []
            for part in parts:
                fn_call = getattr(part, "function_call", None)
                if not fn_call:
                    continue
                tool_name = getattr(fn_call, "name", "unknown")
                args = getattr(fn_call, "args", None)
                input_args = dict(args) if args and not redact else None

                tool_span = ToolCallSpan.record(
                    server_name=agent_name or "gemini",
                    tool_name=tool_name,
                    started_at=started_at,
                    status=ToolCallStatus.SUCCESS,
                    agent_name=agent_name,
                    session_id=session_id,
                    trace_id=trace_id,
                    parent_span_id=llm_span.span_id,
                    span_type="llm_intent",
                    project_id=project_id,
                    input_args=input_args,
                )
                spans.append(tool_span)
    except (AttributeError, TypeError, IndexError):
        pass  # Defensive — don't crash on unexpected response structure

    if spans:
        proxy._emit_spans(spans)
        intent_spans = []
        for s in spans:
            if s.span_type == "llm_intent":
                register_pending_tool(s.tool_name, s.span_id, s.agent_name)
                intent_spans.append(s)
        _maybe_emit_handoffs(intent_spans, proxy)
        logger.debug(
            "llm_wrapper.gemini_traced",
            model=model,
            tool_calls=len(spans) - 1,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


# ---------------------------------------------------------------------------
# Google GenAI (new SDK: google.genai.Client)
# ---------------------------------------------------------------------------


class GenaiClientProxy(_LLMProxyBase):
    """Wraps a ``google.genai.Client`` to auto-trace LLM calls and function calls.

    The new Google GenAI SDK uses a nested property chain::

        client.models.generate_content(model="gemini-2.5-flash", ...)       # sync
        await client.aio.models.generate_content(model="gemini-2.5-flash", ...)  # async

    This proxy intercepts both paths via nested sub-proxies, identical to
    how ``OpenAIProxy`` intercepts ``client.chat.completions.create()``.
    """

    @property
    def models(self) -> _GenaiModelsProxy:
        return _GenaiModelsProxy(self)

    @property
    def aio(self) -> _GenaiAioProxy:
        return _GenaiAioProxy(self)


class _GenaiModelsProxy:
    """Proxy for ``client.models`` that intercepts ``generate_content()``."""

    def __init__(self, parent: GenaiClientProxy) -> None:
        self._parent = parent

    def generate_content(self, *, model: str, **kwargs: Any) -> Any:
        """Intercept sync models.generate_content()."""
        client = object.__getattribute__(self._parent, "_client")
        started_at = datetime.now(UTC)
        status = ToolCallStatus.SUCCESS
        error: str | None = None
        response: Any = None
        try:
            response = client.models.generate_content(model=model, **kwargs)
            return response
        except TimeoutError as exc:
            status = ToolCallStatus.TIMEOUT
            error = f"{type(exc).__name__}: {exc}"
            raise
        except asyncio.CancelledError as exc:
            status = ToolCallStatus.TIMEOUT
            error = f"CancelledError: {exc or 'request cancelled'}"
            raise
        except BaseException as exc:  # noqa: BLE001
            status = ToolCallStatus.ERROR
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            _process_gemini_response(
                self._parent,
                response,
                kwargs,
                started_at,
                model_override=model,
                status=status,
                error=error,
            )

    def generate_content_stream(self, *, model: str, **kwargs: Any) -> Any:
        """Pass through sync streaming — trace the call start only."""
        client = object.__getattribute__(self._parent, "_client")
        started_at = datetime.now(UTC)
        # Record the generation span immediately (we can't intercept stream end)
        _process_gemini_response(
            self._parent,
            _NullResponse(),
            kwargs,
            started_at,
            model_override=model,
        )
        return client.models.generate_content_stream(model=model, **kwargs)

    def __getattr__(self, name: str) -> Any:
        client = object.__getattribute__(self._parent, "_client")
        return getattr(client.models, name)


class _GenaiAioProxy:
    """Proxy for ``client.aio`` that returns an async models proxy."""

    def __init__(self, parent: GenaiClientProxy) -> None:
        self._parent = parent

    @property
    def models(self) -> _GenaiAioModelsProxy:
        return _GenaiAioModelsProxy(self._parent)

    def __getattr__(self, name: str) -> Any:
        client = object.__getattribute__(self._parent, "_client")
        return getattr(client.aio, name)


class _GenaiAioModelsProxy:
    """Proxy for ``client.aio.models`` that intercepts async ``generate_content()``."""

    def __init__(self, parent: GenaiClientProxy) -> None:
        self._parent = parent

    async def generate_content(self, *, model: str, **kwargs: Any) -> Any:
        """Intercept async aio.models.generate_content()."""
        client = object.__getattribute__(self._parent, "_client")
        started_at = datetime.now(UTC)
        status = ToolCallStatus.SUCCESS
        error: str | None = None
        response: Any = None
        try:
            response = await client.aio.models.generate_content(model=model, **kwargs)
            return response
        except TimeoutError as exc:
            status = ToolCallStatus.TIMEOUT
            error = f"{type(exc).__name__}: {exc}"
            raise
        except asyncio.CancelledError as exc:
            status = ToolCallStatus.TIMEOUT
            error = f"CancelledError: {exc or 'request cancelled'}"
            raise
        except BaseException as exc:  # noqa: BLE001
            status = ToolCallStatus.ERROR
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            _process_gemini_response(
                self._parent,
                response,
                kwargs,
                started_at,
                model_override=model,
                status=status,
                error=error,
            )

    async def generate_content_stream(self, *, model: str, **kwargs: Any) -> Any:
        """Pass through async streaming — trace the call start only."""
        client = object.__getattribute__(self._parent, "_client")
        started_at = datetime.now(UTC)
        _process_gemini_response(
            self._parent,
            _NullResponse(),
            kwargs,
            started_at,
            model_override=model,
        )
        return client.aio.models.generate_content_stream(model=model, **kwargs)

    def __getattr__(self, name: str) -> Any:
        client = object.__getattribute__(self._parent, "_client")
        return getattr(client.aio.models, name)


class _NullResponse:
    """Stub response for streaming calls where we can't inspect the full response."""

    candidates: list[Any] = []
    usage_metadata = None


# ---------------------------------------------------------------------------
# Auto-detection factory
# ---------------------------------------------------------------------------


def wrap_llm(
    client: Any,
    langsight: Any,
    agent_name: str | None = None,
    session_id: str | None = None,
    trace_id: str | None = None,
) -> Any:
    """Auto-detect the LLM SDK and return the appropriate wrapper.

    Supports:
    - ``openai.OpenAI`` / ``openai.AsyncOpenAI``
    - ``anthropic.Anthropic`` / ``anthropic.AsyncAnthropic``
    - ``google.genai.Client`` (new SDK)
    - ``google.generativeai.GenerativeModel`` (legacy SDK)

    Returns the original client if the SDK is not recognized (fail-open).
    """
    cls_name = type(client).__name__
    module = type(client).__module__ or ""

    # OpenAI
    if "openai" in module or cls_name in ("OpenAI", "AsyncOpenAI"):
        logger.debug("llm_wrapper.detected", sdk="openai", client_type=cls_name)
        return OpenAIProxy(client, langsight, agent_name, session_id, trace_id)

    # Anthropic
    if "anthropic" in module or cls_name in ("Anthropic", "AsyncAnthropic"):
        logger.debug("llm_wrapper.detected", sdk="anthropic", client_type=cls_name)
        return AnthropicProxy(client, langsight, agent_name, session_id, trace_id)

    # New google.genai.Client — check BEFORE the legacy SDK (more specific match)
    if cls_name == "Client" and "google.genai" in module:
        logger.debug("llm_wrapper.detected", sdk="google-genai", client_type=cls_name)
        return GenaiClientProxy(client, langsight, agent_name, session_id, trace_id)

    # Legacy google.generativeai.GenerativeModel
    if "generativeai" in module or cls_name == "GenerativeModel":
        logger.debug("llm_wrapper.detected", sdk="gemini-legacy", client_type=cls_name)
        return GeminiProxy(client, langsight, agent_name, session_id, trace_id)

    # Unknown — return original (fail-open)
    logger.warning("llm_wrapper.unknown_sdk", client_type=cls_name, module=module)
    return client
