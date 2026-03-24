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

    # Gemini
    import google.generativeai as genai
    model = ls.wrap_llm(genai.GenerativeModel("gemini-2.5-flash"), agent_name="analyst")

The wrapper is transparent — all attributes and methods forward to the
original client. Only the main generation method is intercepted.

Does NOT import any LLM SDK at module level. Detection is lazy.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import structlog

from langsight.sdk.models import ToolCallSpan, ToolCallStatus

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
        return getattr(object.__getattribute__(self, "_client"), name)

    def _emit_spans(self, spans: list[ToolCallSpan]) -> None:
        """Fire-and-forget send spans to LangSight."""
        import asyncio
        import threading

        langsight = object.__getattribute__(self, "_langsight")
        coro = langsight.send_spans(spans)
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running() and not loop.is_closed():
                loop.create_task(coro)
                return
        except RuntimeError:
            pass
        thread = threading.Thread(target=asyncio.run, args=(coro,), daemon=True)
        thread.start()


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
    def __init__(self, parent: OpenAIProxy) -> None:
        self._parent = parent

    @property
    def completions(self) -> _OpenAICompletionsProxy:
        return _OpenAICompletionsProxy(self._parent)


class _OpenAICompletionsProxy:
    def __init__(self, parent: OpenAIProxy) -> None:
        self._parent = parent

    def create(self, **kwargs: Any) -> Any:
        """Intercept sync chat.completions.create()."""
        client = object.__getattribute__(self._parent, "_client")
        started_at = datetime.now(UTC)
        response = client.chat.completions.create(**kwargs)
        _process_openai_response(self._parent, response, kwargs, started_at)
        return response

    async def acreate(self, **kwargs: Any) -> Any:
        """Intercept async chat.completions.create()."""
        client = object.__getattribute__(self._parent, "_client")
        started_at = datetime.now(UTC)
        response = await client.chat.completions.create(**kwargs)
        _process_openai_response(self._parent, response, kwargs, started_at)
        return response


def _process_openai_response(
    proxy: OpenAIProxy, response: Any, kwargs: dict[str, Any], started_at: datetime
) -> None:
    """Extract tool calls and token usage from an OpenAI response."""
    agent_name = object.__getattribute__(proxy, "_agent_name")
    session_id = object.__getattribute__(proxy, "_session_id")
    trace_id = object.__getattribute__(proxy, "_trace_id")
    project_id = object.__getattribute__(proxy, "_project_id")
    redact = object.__getattribute__(proxy, "_redact")

    model = getattr(response, "model", kwargs.get("model", "unknown"))
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "prompt_tokens", None) if usage else None
    output_tokens = getattr(usage, "completion_tokens", None) if usage else None

    spans: list[ToolCallSpan] = []

    # LLM generation span
    llm_span = ToolCallSpan.record(
        server_name="openai",
        tool_name=f"generate/{model}",
        started_at=started_at,
        status=ToolCallStatus.SUCCESS,
        agent_name=agent_name,
        session_id=session_id,
        trace_id=trace_id,
        span_type="agent",
        project_id=project_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model_id=model,
    )
    spans.append(llm_span)

    # Tool use spans from the response
    choices = getattr(response, "choices", [])
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
                span_type="tool_call",
                project_id=project_id,
                input_args=input_args,
            )
            spans.append(tool_span)

    if spans:
        proxy._emit_spans(spans)
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
    def __init__(self, parent: AnthropicProxy) -> None:
        self._parent = parent

    def create(self, **kwargs: Any) -> Any:
        """Intercept sync messages.create()."""
        client = object.__getattribute__(self._parent, "_client")
        started_at = datetime.now(UTC)
        response = client.messages.create(**kwargs)
        _process_anthropic_response(self._parent, response, kwargs, started_at)
        return response

    async def acreate(self, **kwargs: Any) -> Any:
        """Intercept async messages.create()."""
        client = object.__getattribute__(self._parent, "_client")
        started_at = datetime.now(UTC)
        response = await client.messages.create(**kwargs)
        _process_anthropic_response(self._parent, response, kwargs, started_at)
        return response


def _process_anthropic_response(
    proxy: AnthropicProxy, response: Any, kwargs: dict[str, Any], started_at: datetime
) -> None:
    """Extract tool_use blocks and token usage from an Anthropic response."""
    agent_name = object.__getattribute__(proxy, "_agent_name")
    session_id = object.__getattribute__(proxy, "_session_id")
    trace_id = object.__getattribute__(proxy, "_trace_id")
    project_id = object.__getattribute__(proxy, "_project_id")
    redact = object.__getattribute__(proxy, "_redact")

    model = getattr(response, "model", kwargs.get("model", "unknown"))
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "input_tokens", None) if usage else None
    output_tokens = getattr(usage, "output_tokens", None) if usage else None

    spans: list[ToolCallSpan] = []

    # LLM generation span
    llm_span = ToolCallSpan.record(
        server_name="anthropic",
        tool_name=f"generate/{model}",
        started_at=started_at,
        status=ToolCallStatus.SUCCESS,
        agent_name=agent_name,
        session_id=session_id,
        trace_id=trace_id,
        span_type="agent",
        project_id=project_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model_id=model,
    )
    spans.append(llm_span)

    # Tool use spans from content blocks
    content = getattr(response, "content", []) or []
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
            span_type="tool_call",
            project_id=project_id,
            input_args=input_args if isinstance(input_args, dict) else None,
        )
        spans.append(tool_span)

    if spans:
        proxy._emit_spans(spans)
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
        response = client.generate_content(*args, **kwargs)
        _process_gemini_response(self, response, kwargs, started_at)
        return response

    async def generate_content_async(self, *args: Any, **kwargs: Any) -> Any:
        """Intercept async generate_content_async()."""
        client = object.__getattribute__(self, "_client")
        started_at = datetime.now(UTC)
        response = await client.generate_content_async(*args, **kwargs)
        _process_gemini_response(self, response, kwargs, started_at)
        return response


def _process_gemini_response(
    proxy: GeminiProxy, response: Any, kwargs: dict[str, Any], started_at: datetime
) -> None:
    """Extract function calls and token usage from a Gemini response."""
    agent_name = object.__getattribute__(proxy, "_agent_name")
    session_id = object.__getattribute__(proxy, "_session_id")
    trace_id = object.__getattribute__(proxy, "_trace_id")
    project_id = object.__getattribute__(proxy, "_project_id")
    redact = object.__getattribute__(proxy, "_redact")

    # Model name from the wrapped model object
    client = object.__getattribute__(proxy, "_client")
    model = getattr(client, "model_name", None) or getattr(client, "_model_name", "gemini")

    # Token usage from usage_metadata
    usage = getattr(response, "usage_metadata", None)
    input_tokens = getattr(usage, "prompt_token_count", None) if usage else None
    output_tokens = getattr(usage, "candidates_token_count", None) if usage else None

    spans: list[ToolCallSpan] = []

    # LLM generation span
    llm_span = ToolCallSpan.record(
        server_name="gemini",
        tool_name=f"generate/{model}",
        started_at=started_at,
        status=ToolCallStatus.SUCCESS,
        agent_name=agent_name,
        session_id=session_id,
        trace_id=trace_id,
        span_type="agent",
        project_id=project_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model_id=model,
    )
    spans.append(llm_span)

    # Function call spans from response parts
    try:
        candidates = getattr(response, "candidates", []) or []
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
                    span_type="tool_call",
                    project_id=project_id,
                    input_args=input_args,
                )
                spans.append(tool_span)
    except (AttributeError, TypeError, IndexError):
        pass  # Defensive — don't crash on unexpected response structure

    if spans:
        proxy._emit_spans(spans)
        logger.debug(
            "llm_wrapper.gemini_traced",
            model=model,
            tool_calls=len(spans) - 1,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


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
    - ``google.generativeai.GenerativeModel``

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

    # Gemini
    if "google" in module or "generativeai" in module or cls_name == "GenerativeModel":
        logger.debug("llm_wrapper.detected", sdk="gemini", client_type=cls_name)
        return GeminiProxy(client, langsight, agent_name, session_id, trace_id)

    # Unknown — return original (fail-open)
    logger.warning("llm_wrapper.unknown_sdk", client_type=cls_name, module=module)
    return client
