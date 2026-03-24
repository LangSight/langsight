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
from datetime import UTC, datetime
from typing import Any

import structlog

from langsight.sdk.context import register_pending_tool
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
            _process_openai_response(self._parent, response, kwargs, started_at, status=status, error=error)

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
            _process_openai_response(self._parent, response, kwargs, started_at, status=status, error=error)


def _process_openai_response(
    proxy: OpenAIProxy,
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

    model = getattr(response, "model", kwargs.get("model", "unknown")) if response is not None else kwargs.get("model", "unknown")
    usage = getattr(response, "usage", None) if response is not None else None
    input_tokens = getattr(usage, "prompt_tokens", None) if usage else None
    output_tokens = getattr(usage, "completion_tokens", None) if usage else None

    spans: list[ToolCallSpan] = []

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
    )
    spans.append(llm_span)

    # Tool use spans from the response — only on success
    choices = getattr(response, "choices", []) if response is not None and status == ToolCallStatus.SUCCESS else []
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
        # Register tool_call spans so wrap() can claim them as parents
        for s in spans:
            if s.span_type == "tool_call":
                register_pending_tool(s.tool_name, s.span_id, s.agent_name)
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
            _process_anthropic_response(self._parent, response, kwargs, started_at, status=status, error=error)

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
            _process_anthropic_response(self._parent, response, kwargs, started_at, status=status, error=error)


def _process_anthropic_response(
    proxy: AnthropicProxy,
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

    model = getattr(response, "model", kwargs.get("model", "unknown")) if response is not None else kwargs.get("model", "unknown")
    usage = getattr(response, "usage", None) if response is not None else None
    input_tokens = getattr(usage, "input_tokens", None) if usage else None
    output_tokens = getattr(usage, "output_tokens", None) if usage else None

    spans: list[ToolCallSpan] = []

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
    )
    spans.append(llm_span)

    # Tool use spans from content blocks — only on success
    content = (getattr(response, "content", []) or []) if response is not None and status == ToolCallStatus.SUCCESS else []
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
        for s in spans:
            if s.span_type == "tool_call":
                register_pending_tool(s.tool_name, s.span_id, s.agent_name)
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
    proxy: _LLMProxyBase,
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
        model = getattr(client, "model_name", None) or getattr(client, "_model_name", "gemini")

    # Token usage from usage_metadata — only available on success
    usage = getattr(response, "usage_metadata", None) if response is not None else None
    input_tokens = getattr(usage, "prompt_token_count", None) if usage else None
    output_tokens = getattr(usage, "candidates_token_count", None) if usage else None

    spans: list[ToolCallSpan] = []

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
    )
    spans.append(llm_span)

    # Function call spans from response parts — only on success
    try:
        candidates = (getattr(response, "candidates", []) or []) if response is not None and status == ToolCallStatus.SUCCESS else []
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
        for s in spans:
            if s.span_type == "tool_call":
                register_pending_tool(s.tool_name, s.span_id, s.agent_name)
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
            _process_gemini_response(self._parent, response, kwargs, started_at, model_override=model, status=status, error=error)

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
            _process_gemini_response(self._parent, response, kwargs, started_at, model_override=model, status=status, error=error)

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
