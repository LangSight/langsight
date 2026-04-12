"""
Monkey-patch auto-instrumentation — patches LLM SDK classes and MCP at import time.

After calling ``auto_patch()``, every LLM client you create is automatically
traced, every MCP tool call is automatically traced, and agent handoffs are
auto-detected — no ``wrap_llm()``, no ``wrap()``, no ``create_handoff()`` needed.

The simplest multi-agent integration (v0.12.0)::

    import langsight
    langsight.auto_patch()   # LLM + MCP + handoffs — all automatic

    async with langsight.session(agent_name="orchestrator") as session_id:
        client = OpenAI()                           # LLM calls: auto-traced
        result = await mcp_session.call_tool(...)   # MCP calls: auto-traced
        # When LLM calls "call_analyst" tool → handoff span auto-emitted

Multi-agent without any boilerplate::

    import langsight
    langsight.auto_patch()

    async def orchestrator(question: str):
        async with langsight.session(agent_name="orchestrator"):
            # All LLM + MCP calls auto-traced. When the LLM selects
            # "call_analyst" as a tool, a handoff span is emitted automatically.
            response = await llm.generate(question, tools=[call_analyst_tool])

    async def analyst(question: str):
        async with langsight.session(agent_name="analyst"):
            # MCP call auto-traced — no wrap() needed
            data = await mcp.call_tool("search_products", {"q": question})
            return data

Context inheritance via contextvars (v0.12.0):

    ``wrap()`` and ``wrap_llm()`` now read ``_agent_ctx``, ``_session_ctx``, and
    ``_trace_ctx`` as fallback when ``agent_name``, ``session_id``, or ``trace_id``
    are not explicitly provided. Inside a ``langsight.session()`` block all wrap
    calls inherit context automatically — no parameter threading needed.

Handoff auto-detection (v0.12.0):

    When an LLM selects a tool whose name matches the pattern::

        call_*  |  delegate_*  |  invoke_*  |  transfer_to_*  |  run_*  |  dispatch_*

    LangSight automatically emits an explicit handoff span to the target agent.
    For example, ``call_analyst`` produces a handoff span from the current agent
    to ``analyst``. The dashboard renders this as a solid edge instead of a
    timing-inferred dashed edge. No ``create_handoff()`` call is required.

MCP auto-patch (v0.12.0):

    ``auto_patch()`` now also calls ``_patch_mcp()``, which monkey-patches
    ``mcp.ClientSession.call_tool``. Every MCP tool call after ``auto_patch()``
    is automatically traced with the correct ``agent_name``, ``session_id``,
    and ``trace_id`` from the active ``session()`` context. No ``ls.wrap()``
    call is needed.

Coexistence with Langfuse::

    from langfuse.decorators import observe
    import langsight

    langsight.auto_patch()   # MCP + handoffs + lineage (zero decorators)

    @observe()               # LLM prompt/completion tracing (Langfuse)
    async def my_agent(query):
        response = await llm.generate(...)    # Both Langfuse + LangSight trace this
        data = await mcp.call_tool(...)       # LangSight traces this (auto)
        return response

Supported SDKs (all optional — missing SDKs are skipped):
  - openai  (OpenAI, AsyncOpenAI)
  - anthropic  (Anthropic, AsyncAnthropic)
  - google.genai  (new SDK: google-genai)
  - google.generativeai  (legacy SDK: google-generativeai)
  - mcp  (mcp.ClientSession.call_tool)
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from langsight.sdk.models import ToolCallSpan, ToolCallStatus

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Async-safe context variables — each asyncio task inherits parent context.
# ContextVar is the correct primitive for this: thread-safe + task-safe.
# ---------------------------------------------------------------------------

_session_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "langsight_session_id", default=None
)
_agent_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "langsight_agent_name", default=None
)
_trace_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "langsight_trace_id", default=None
)
_parent_span_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "langsight_parent_span_id", default=None
)
# Set to True by MCPClientProxy.call_tool() to suppress auto_patch for the
# inner ClientSession.call_tool() call — prevents double-tracing when both
# explicit wrap() and auto_patch() are active for the same MCP session.
_mcp_proxy_active: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "langsight_mcp_proxy_active", default=False
)
# Set to True when _patch_langgraph() has already injected a callback into the
# current Pregel call chain — prevents double-injection when invoke() internally
# calls stream() (which it does in all LangGraph versions).
_lg_callback_injected: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "langsight_lg_callback_injected", default=False
)

# ---------------------------------------------------------------------------
# Module-level state — patched SDK originals + global client
# ---------------------------------------------------------------------------

_originals: dict[str, Any] = {}  # original SDK methods, keyed by SDK name
_patched_sdks: set[str] = set()  # set of patched SDK names
_global_client: Any | None = None  # LangSightClient singleton (avoids circular import)

# Deferred init params — stored when auto_patch() is called without LANGSIGHT_URL.
# On first span, _resolve_client() tries to create the client using these + env vars.
_deferred_init: dict[str, Any] | None = None


def _resolve_client() -> Any | None:
    """Return the global client, initialising it lazily if env vars are now available.

    Called on every span emit.  If auto_patch() was called before the .env was
    loaded, the client will be None.  This function re-attempts initialisation
    once env vars become available — transparent to the user.
    """
    global _global_client, _deferred_init
    if _global_client is not None:
        return _global_client
    if _deferred_init is None:
        return None
    import os

    from langsight.sdk import init  # lazy

    # Check if env vars are now available
    if not (os.environ.get("LANGSIGHT_URL") or _deferred_init.get("url")):
        return None

    ls = init(**_deferred_init)
    if ls is not None:
        _global_client = ls
        _deferred_init = None  # clear — no longer needed
        logger.info("auto_patch.lazy_init", message="LangSight client initialised on first span.")
    return _global_client


# ---------------------------------------------------------------------------
# Minimal proxy shim — satisfies the duck-typing expected by
# _process_openai_response / _process_anthropic_response / _process_gemini_response.
# ---------------------------------------------------------------------------


class _AutoPatchProxy:
    """Lightweight shim that satisfies _LLMProxyBase duck-type."""

    def __init__(
        self,
        ls: Any,
        agent_name: str | None = None,
        session_id: str | None = None,
        trace_id: str | None = None,
        parent_span_id: str | None = None,
    ) -> None:
        object.__setattr__(self, "_langsight", ls)
        object.__setattr__(self, "_agent_name", agent_name)
        object.__setattr__(self, "_session_id", session_id)
        object.__setattr__(self, "_trace_id", trace_id)
        object.__setattr__(self, "_redact", getattr(ls, "_redact_payloads", False))
        object.__setattr__(self, "_project_id", getattr(ls, "_project_id", None) or "")
        object.__setattr__(self, "_parent_span_id", parent_span_id)

    def _emit_spans(self, spans: list[ToolCallSpan]) -> None:
        """Forward spans to the global LangSight client buffer."""
        ls = object.__getattribute__(self, "_langsight")
        for span in spans:
            ls.buffer_span(span)


def _make_proxy() -> _AutoPatchProxy | None:
    """Return a proxy for the current context, or None if not configured."""
    if _global_client is None:
        return None
    return _AutoPatchProxy(
        _global_client,
        agent_name=_agent_ctx.get() or None,
        session_id=_session_ctx.get() or None,
        trace_id=_trace_ctx.get() or None,
        parent_span_id=_parent_span_ctx.get() or None,
    )


# ---------------------------------------------------------------------------
# Per-SDK patching — reuses existing _process_*_response() functions
# ---------------------------------------------------------------------------


def _patch_openai() -> None:
    """Patch openai.OpenAI / AsyncOpenAI chat completion methods."""
    try:
        import openai  # noqa: F401
    except ImportError:
        return

    from langsight.sdk.llm_wrapper import _process_openai_response  # lazy import

    # ── Sync patch ──────────────────────────────────────────────────────────
    try:
        from openai.resources.chat.completions import Completions

        orig_sync = Completions.create
        _originals["openai_sync"] = orig_sync

        def _patched_sync(self_sdk: Any, **kwargs: Any) -> Any:
            proxy = _make_proxy()
            if proxy is None:
                return orig_sync(self_sdk, **kwargs)
            started_at = datetime.now(UTC)
            status = ToolCallStatus.SUCCESS
            error: str | None = None
            response: Any = None
            try:
                response = orig_sync(self_sdk, **kwargs)
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
                    proxy, response, kwargs, started_at, status=status, error=error
                )

        Completions.create = _patched_sync  # type: ignore[method-assign, assignment]
    except (ImportError, AttributeError):
        pass

    # ── Async patch ─────────────────────────────────────────────────────────
    try:
        from openai.resources.chat.completions import AsyncCompletions

        orig_async = AsyncCompletions.create
        _originals["openai_async"] = orig_async

        async def _patched_async(self_sdk: Any, **kwargs: Any) -> Any:
            proxy = _make_proxy()
            if proxy is None:
                return await orig_async(self_sdk, **kwargs)
            started_at = datetime.now(UTC)
            status = ToolCallStatus.SUCCESS
            error: str | None = None
            response: Any = None
            try:
                response = await orig_async(self_sdk, **kwargs)
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
                    proxy, response, kwargs, started_at, status=status, error=error
                )

        AsyncCompletions.create = _patched_async  # type: ignore[method-assign, assignment]
    except (ImportError, AttributeError):
        pass

    _patched_sdks.add("openai")
    logger.debug("auto_patch.patched", sdk="openai")


def _patch_anthropic() -> None:
    """Patch anthropic.Anthropic / AsyncAnthropic messages.create methods."""
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return

    from langsight.sdk.llm_wrapper import _process_anthropic_response  # lazy import

    # ── Sync patch ──────────────────────────────────────────────────────────
    try:
        from anthropic.resources.messages import Messages

        orig_sync = Messages.create
        _originals["anthropic_sync"] = orig_sync

        def _patched_sync(self_sdk: Any, **kwargs: Any) -> Any:
            proxy = _make_proxy()
            if proxy is None:
                return orig_sync(self_sdk, **kwargs)
            started_at = datetime.now(UTC)
            status = ToolCallStatus.SUCCESS
            error: str | None = None
            response: Any = None
            try:
                response = orig_sync(self_sdk, **kwargs)
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
                    proxy, response, kwargs, started_at, status=status, error=error
                )

        Messages.create = _patched_sync  # type: ignore[method-assign, assignment]
    except (ImportError, AttributeError):
        pass

    # ── Async patch ─────────────────────────────────────────────────────────
    try:
        from anthropic.resources.messages import AsyncMessages

        orig_async = AsyncMessages.create
        _originals["anthropic_async"] = orig_async

        async def _patched_async(self_sdk: Any, **kwargs: Any) -> Any:
            proxy = _make_proxy()
            if proxy is None:
                return await orig_async(self_sdk, **kwargs)
            started_at = datetime.now(UTC)
            status = ToolCallStatus.SUCCESS
            error: str | None = None
            response: Any = None
            try:
                response = await orig_async(self_sdk, **kwargs)
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
                    proxy, response, kwargs, started_at, status=status, error=error
                )

        AsyncMessages.create = _patched_async  # type: ignore[method-assign, assignment]
    except (ImportError, AttributeError):
        pass

    _patched_sdks.add("anthropic")
    logger.debug("auto_patch.patched", sdk="anthropic")


def _patch_google_genai() -> None:
    """Patch google.genai.Client models.generate_content (new SDK)."""
    try:
        import google.genai  # noqa: F401
    except ImportError:
        return

    from langsight.sdk.llm_wrapper import _process_gemini_response  # lazy import

    # ── Sync patch (client.models.generate_content) ────────────────────────
    try:
        from google.genai import models as _genai_models

        orig_sync = _genai_models.Models.generate_content
        _originals["genai_sync"] = orig_sync

        def _patched_sync(self_sdk: Any, *, model: str, **kwargs: Any) -> Any:
            proxy = _make_proxy()
            if proxy is None:
                return orig_sync(self_sdk, model=model, **kwargs)
            started_at = datetime.now(UTC)
            status = ToolCallStatus.SUCCESS
            error: str | None = None
            response: Any = None
            try:
                response = orig_sync(self_sdk, model=model, **kwargs)
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
                    proxy,
                    response,
                    kwargs,
                    started_at,
                    model_override=model,
                    status=status,
                    error=error,
                )

        _genai_models.Models.generate_content = _patched_sync
    except (ImportError, AttributeError):
        pass

    # ── Async patch (client.aio.models.generate_content) ──────────────────
    try:
        from google.genai import models as _genai_models

        orig_async = _genai_models.AsyncModels.generate_content
        _originals["genai_async"] = orig_async

        async def _patched_async(self_sdk: Any, *, model: str, **kwargs: Any) -> Any:
            proxy = _make_proxy()
            if proxy is None:
                return await orig_async(self_sdk, model=model, **kwargs)
            started_at = datetime.now(UTC)
            status = ToolCallStatus.SUCCESS
            error: str | None = None
            response: Any = None
            try:
                response = await orig_async(self_sdk, model=model, **kwargs)
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
                    proxy,
                    response,
                    kwargs,
                    started_at,
                    model_override=model,
                    status=status,
                    error=error,
                )

        _genai_models.AsyncModels.generate_content = _patched_async
    except (ImportError, AttributeError):
        pass

    _patched_sdks.add("google_genai")
    logger.debug("auto_patch.patched", sdk="google.genai")


def _patch_google_generativeai() -> None:
    """Patch google.generativeai.GenerativeModel (legacy SDK)."""
    try:
        import google.generativeai  # noqa: F401
    except ImportError:
        return

    from langsight.sdk.llm_wrapper import _process_gemini_response  # lazy import

    try:
        from google.generativeai.generative_models import GenerativeModel

        orig_sync = GenerativeModel.generate_content
        orig_async = GenerativeModel.generate_content_async
        _originals["genai_legacy_sync"] = orig_sync
        _originals["genai_legacy_async"] = orig_async

        def _patched_sync(self_sdk: Any, *args: Any, **kwargs: Any) -> Any:
            proxy = _make_proxy()
            if proxy is None:
                return orig_sync(self_sdk, *args, **kwargs)
            # For legacy SDK, model name comes from model.model_name attribute
            started_at = datetime.now(UTC)
            status = ToolCallStatus.SUCCESS
            error: str | None = None
            response: Any = None
            # Attach client ref so _process_gemini_response can read model_name
            object.__setattr__(proxy, "_client", self_sdk)
            try:
                response = orig_sync(self_sdk, *args, **kwargs)
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
                    proxy, response, kwargs, started_at, status=status, error=error
                )

        async def _patched_async(self_sdk: Any, *args: Any, **kwargs: Any) -> Any:
            proxy = _make_proxy()
            if proxy is None:
                return await orig_async(self_sdk, *args, **kwargs)
            object.__setattr__(proxy, "_client", self_sdk)
            started_at = datetime.now(UTC)
            status = ToolCallStatus.SUCCESS
            error: str | None = None
            response: Any = None
            try:
                response = await orig_async(self_sdk, *args, **kwargs)
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
                    proxy, response, kwargs, started_at, status=status, error=error
                )

        GenerativeModel.generate_content = _patched_sync
        GenerativeModel.generate_content_async = _patched_async
    except (ImportError, AttributeError):
        pass

    _patched_sdks.add("google_generativeai")
    logger.debug("auto_patch.patched", sdk="google.generativeai")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _patch_claude_sdk() -> None:
    """Patch ``claude_agent_sdk.ClaudeAgentOptions.__init__`` to auto-inject
    LangSight hooks into every agent run — zero user code changes required.

    When ``auto_patch()`` is called, this function patches the ``ClaudeAgentOptions``
    dataclass so that every instantiation automatically receives LangSight's
    tracing hooks.  The hooks capture:

    - ``UserPromptSubmit``  → session span with ``llm_input`` (human prompt)
    - ``PreToolUse``        → tool_call span start (name + args)
    - ``PostToolUse``       → tool_call span complete (name + args + response)
    - ``PostToolUseFailure``→ tool_call span with status=error
    - ``SubagentStart``     → handoff span + marks sub-agent as active for session
    - ``SubagentStop``      → clears sub-agent active state (reverts to coordinator)
    - ``Stop``              → session span with ``llm_output`` (final response)

    The user does nothing — no hooks dict, no code changes.  Just:
        ``LANGSIGHT_URL=http://localhost:8000 python app.py``

    Safe to call multiple times (idempotent via ``_patched_sdks``).
    No-op when ``claude_agent_sdk`` is not installed.
    """
    if "claude_sdk" in _patched_sdks:
        return

    try:
        import claude_agent_sdk as _csdk  # noqa: F401 — import check only
        from claude_agent_sdk import ClaudeAgentOptions
    except ImportError:
        return

    orig_init = ClaudeAgentOptions.__init__
    _originals["claude_sdk_init"] = orig_init

    def _patched_init(self_sdk: Any, *args: Any, **kw: Any) -> None:
        # Call original __init__ first so all fields are set
        orig_init(self_sdk, *args, **kw)

        # Build our hooks and merge with any the user already configured
        ls_hooks = _build_claude_sdk_hooks()
        if not ls_hooks:
            return  # no global client yet — skip

        existing: dict[Any, list[Any]] = self_sdk.hooks or {}
        merged: dict[Any, list[Any]] = {}
        for event, matchers in ls_hooks.items():
            # Prepend LangSight matchers so we always fire, regardless of user hooks
            merged[event] = matchers + list(existing.get(event, []))
        # Carry over any user hook events we don't handle
        for event, matchers in existing.items():
            if event not in merged:
                merged[event] = matchers
        object.__setattr__(self_sdk, "hooks", merged) if hasattr(
            type(self_sdk), "__dataclass_fields__"
        ) else setattr(self_sdk, "hooks", merged)

    ClaudeAgentOptions.__init__ = _patched_init
    _patched_sdks.add("claude_sdk")
    logger.debug("auto_patch.patched", sdk="claude_sdk")


def _patch_crewai() -> None:
    """Instrument CrewAI for LangSight observability.

    **Primary path (CrewAI >= 1.5 with event bus)**:
    Registers a :class:`~langsight.integrations.crewai_events.LangSightCrewAIEventListener`
    on the native ``crewai_event_bus``.  This captures crew / task / agent /
    tool / LLM lifecycle spans with full attribution (agent_role, task_name,
    task_id) — richer and more forward-compatible than monkey-patching.

    **Fallback path (older CrewAI)**:
    Monkey-patches ``BaseTool.run``, ``Agent.kickoff``, and ``Crew.kickoff``
    to capture tool calls and agent context.

    **Always installed (both paths)**:
    - ``Agent.kickoff`` patch — sets ``_agent_ctx`` so the Anthropic/OpenAI
      SDK patches attribute LLM calls to the active CrewAI agent role.
    - ``Crew.kickoff`` patch — auto-generates ``session_id`` and flushes
      buffered spans after kickoff completes.

    Safe to call multiple times (idempotent via ``_patched_sdks``).
    No-op when ``crewai`` is not installed.
    """
    if "crewai" in _patched_sdks:
        return

    try:
        import crewai as _crewai  # noqa: F401 — import check only
        from crewai import Crew
    except ImportError:
        return

    # ------------------------------------------------------------------
    # Try event bus first (CrewAI >= 1.5).  If available, this replaces
    # the BaseTool.run monkey-patch with richer event-driven spans.
    # ------------------------------------------------------------------
    _event_bus_active = False
    try:
        from langsight.integrations.crewai_events import LangSightCrewAIEventListener

        _listener = LangSightCrewAIEventListener(client_resolver=_resolve_client)
        _event_bus_active = _listener.setup()
        if _event_bus_active:
            logger.info("auto_patch.crewai.event_bus", status="active")
    except Exception as _eb_exc:  # noqa: BLE001
        logger.debug("auto_patch.crewai.event_bus_failed", error=str(_eb_exc))

    # ------------------------------------------------------------------
    # Fallback: Patch BaseTool.run — only when event bus is NOT active.
    # Event bus ToolUsageFinishedEvent is richer (has agent_role, task_name,
    # tool_args, started_at/finished_at, from_cache).
    # ------------------------------------------------------------------
    if not _event_bus_active:
        from datetime import UTC
        from datetime import datetime as _dt_crewai

        from langsight.sdk.models import ToolCallSpan as _ToolCallSpan
        from langsight.sdk.models import ToolCallStatus as _ToolCallStatus

        try:
            from crewai.tools.base_tool import BaseTool
        except ImportError:
            BaseTool = None  # noqa: F841

        if BaseTool is not None:
            orig_base_tool_run = BaseTool.run
            _originals["crewai_base_tool_run"] = orig_base_tool_run

            def _patched_base_tool_run(self_tool: Any, *args: Any, **kw: Any) -> Any:
                raw_name: str = getattr(self_tool, "name", "unknown") or "unknown"
                server_name = "crewai"
                tool_name = raw_name
                if "__" in raw_name:
                    parts = raw_name.split("__", 2)
                    if len(parts) >= 2:
                        server_name = parts[1]
                    if len(parts) == 3:
                        tool_name = parts[2]

                agent_name: str = _agent_ctx.get() or ""
                session_id: str | None = _session_ctx.get()
                started = _dt_crewai.now(UTC)

                try:
                    result = orig_base_tool_run(self_tool, *args, **kw)
                    client = _resolve_client()
                    if client is not None:
                        span = _ToolCallSpan.record(
                            server_name=server_name,
                            tool_name=tool_name,
                            started_at=started,
                            status=_ToolCallStatus.SUCCESS,
                            agent_name=agent_name or None,
                            session_id=session_id,
                            span_type="tool_call",
                            output_result=str(result)[:2000] if result is not None else None,
                            project_id=getattr(client, "_project_id", None) or None,
                            lineage_provenance="explicit",
                            schema_version="1.0",
                        )
                        client.buffer_span(span)
                    return result
                except Exception as _exc:
                    client = _resolve_client()
                    if client is not None:
                        span = _ToolCallSpan.record(
                            server_name=server_name,
                            tool_name=tool_name,
                            started_at=started,
                            status=_ToolCallStatus.ERROR,
                            error=str(_exc),
                            agent_name=agent_name or None,
                            session_id=session_id,
                            span_type="tool_call",
                            project_id=getattr(client, "_project_id", None) or None,
                            lineage_provenance="explicit",
                            schema_version="1.0",
                        )
                        client.buffer_span(span)
                    raise

            BaseTool.run = _patched_base_tool_run

    # ------------------------------------------------------------------
    # Always patch Agent.kickoff — sets _agent_ctx to agent's role so the
    # Anthropic/OpenAI SDK patches attribute LLM calls to the active agent.
    # This is needed even when the event bus is active because the SDK
    # patches read _agent_ctx from the calling thread's context.
    # ------------------------------------------------------------------
    try:
        from crewai.agent.core import Agent as _CrewAgentCore
    except ImportError:
        _CrewAgentCore = None  # noqa: F841

    if _CrewAgentCore is not None:
        orig_agent_kickoff = getattr(_CrewAgentCore, "kickoff", None)
        if orig_agent_kickoff is not None:
            _originals["crewai_agent_kickoff"] = orig_agent_kickoff

            def _patched_agent_kickoff(self_agent: Any, *args: Any, **kw: Any) -> Any:
                role: str = getattr(self_agent, "role", None) or ""
                token = _agent_ctx.set(role) if role else None
                try:
                    return orig_agent_kickoff(self_agent, *args, **kw)
                finally:
                    if token is not None:
                        _agent_ctx.reset(token)

            _CrewAgentCore.kickoff = _patched_agent_kickoff

    # ------------------------------------------------------------------
    # Also patch Agent.execute_task — CrewAI 1.6+ calls execute_task
    # directly from Crew._run_sequential_process(), bypassing kickoff.
    # This is the MAIN codepath for setting _agent_ctx during crew runs.
    # ------------------------------------------------------------------
    if _CrewAgentCore is not None:
        orig_execute_task = getattr(_CrewAgentCore, "execute_task", None)
        if orig_execute_task is not None:
            _originals["crewai_agent_execute_task"] = orig_execute_task

            def _patched_execute_task(self_agent: Any, *args: Any, **kw: Any) -> Any:
                import uuid as _uuid

                role: str = getattr(self_agent, "role", None) or ""
                token = _agent_ctx.set(role) if role else None
                # Bridge: pre-generate an agent span_id and write it to the
                # shared dict BEFORE orig_execute_task fires the event.
                # The event handler (_handle_agent_started) will adopt this
                # span_id instead of generating its own.
                parent_token = None
                if role:
                    try:
                        from langsight.integrations.crewai_events import (
                            _active_agent_span_ids,
                        )

                        agent_span_id = str(_uuid.uuid4())
                        _active_agent_span_ids[role] = agent_span_id
                        parent_token = _parent_span_ctx.set(agent_span_id)
                    except ImportError:
                        pass
                try:
                    return orig_execute_task(self_agent, *args, **kw)
                finally:
                    if token is not None:
                        _agent_ctx.reset(token)
                    if parent_token is not None:
                        _parent_span_ctx.reset(parent_token)

            _CrewAgentCore.execute_task = _patched_execute_task

    # ------------------------------------------------------------------
    # Always patch Crew.kickoff — auto-create a session_id when none is
    # active, and flush buffered spans after kickoff completes.
    # The event bus listener also handles session + flush, but this patch
    # ensures it works even if the event bus setup partially failed.
    # ------------------------------------------------------------------
    orig_kickoff = getattr(Crew, "kickoff", None)
    if orig_kickoff is None:
        _patched_sdks.add("crewai")
        logger.debug("auto_patch.patched", sdk="crewai")
        return
    _originals["crewai_kickoff"] = orig_kickoff

    def _patched_kickoff(self_crew: Any, *args: Any, **kw: Any) -> Any:
        preexisting_session = bool(_session_ctx.get())
        token = None
        if not preexisting_session:
            import uuid as _uuid

            auto_sid = _uuid.uuid4().hex
            token = _session_ctx.set(auto_sid)
        try:
            return orig_kickoff(self_crew, *args, **kw)
        finally:
            if token is not None:
                _session_ctx.reset(token)
            client = _resolve_client()
            if client is not None:
                import asyncio as _asyncio

                try:
                    loop = _asyncio.get_event_loop()
                    if loop.is_running():
                        _asyncio.ensure_future(client.flush())
                    else:
                        loop.run_until_complete(client.flush())
                except Exception as _flush_exc:  # noqa: BLE001
                    logger.warning("auto_patch.crewai.flush_error", error=str(_flush_exc))

    Crew.kickoff = _patched_kickoff

    _patched_sdks.add("crewai")
    logger.debug(
        "auto_patch.patched",
        sdk="crewai",
        event_bus=_event_bus_active,
    )


def _build_claude_sdk_hooks() -> dict[Any, list[Any]] | None:
    """Build the hooks dict for ``ClaudeAgentOptions`` using the global client.

    Returns ``None`` when the global client is not yet initialised.
    """
    if _global_client is None:
        return None

    try:
        from claude_agent_sdk.types import HookMatcher
    except ImportError:
        return None

    import json as _json
    from datetime import UTC
    from datetime import datetime as _dt

    from langsight.sdk.models import ToolCallSpan, ToolCallStatus

    # Per-session state: keyed by session_id
    # Maps session_id → { "started_at": datetime, "prompt": str }
    _session_state: dict[str, dict[str, Any]] = {}
    # Maps tool_use_id → started_at (for latency computation)
    _tool_started: dict[str, _dt] = {}
    # Tracks which sub-agent is currently active per session.
    # Set by SubagentStart, cleared by SubagentStop.
    # Used to correctly attribute tool calls made by sub-agents.
    # Maps session_id → agent_type (e.g. "sql_analyst")
    _active_subagent: dict[str, str] = {}

    import os as _os

    def _project_id() -> str | None:
        return getattr(_global_client, "_project_id", None) or None

    def _agent_name_for(hook_input: Any, fallback: str = "coordinator") -> str:
        """Derive agent name for a hook event.

        Priority order:
          1. Explicit agent_type in hook_input (set by SDK for some hook types)
          2. Active sub-agent for this session (set by SubagentStart/SubagentStop)
          3. Top-level agent from context var (set by langsight.session())
          4. LANGSIGHT_AGENT_NAME env var
          5. Hardcoded fallback
        """
        # (1) SDK may provide agent_type directly in hook input (sub-agent events)
        if hook_input.get("agent_type"):
            return str(hook_input["agent_type"])
        # (2) Sub-agent lifecycle tracking — most reliable method
        sid = hook_input.get("session_id", "")
        if sid and sid in _active_subagent:
            return _active_subagent[sid]
        # (3) Context var set by langsight.session(agent_name=...)
        return _agent_ctx.get() or _os.environ.get("LANGSIGHT_AGENT_NAME") or fallback

    async def _on_user_prompt(hook_input: Any, _tid: Any, _ctx: Any) -> Any:
        """Capture human prompt → session start span."""
        sid = hook_input.get("session_id", "")
        prompt = hook_input.get("prompt", "")
        started = _dt.now(UTC)
        _session_state[sid] = {"started_at": started, "prompt": prompt}
        # Emit start span with llm_input immediately
        try:
            span = ToolCallSpan.record(
                server_name="claude-sdk",
                tool_name="session",
                started_at=started,
                status=ToolCallStatus.SUCCESS,
                session_id=sid or None,
                agent_name=_agent_name_for(hook_input),
                span_type="agent",
                llm_input=prompt,
                llm_output=None,
                project_id=_project_id(),
                lineage_provenance="explicit",
                schema_version="1.0",
            )
            await _global_client._post_spans([span])
        except Exception:  # noqa: BLE001
            pass
        return {"continue_": True}

    async def _on_pre_tool(hook_input: Any, _tid: Any, _ctx: Any) -> Any:
        """Record tool call start time."""
        tool_use_id = hook_input.get("tool_use_id", "")
        if tool_use_id:
            _tool_started[tool_use_id] = _dt.now(UTC)
        return {"continue_": True}

    async def _on_post_tool(hook_input: Any, _tid: Any, _ctx: Any) -> Any:
        """Capture tool call completion → tool_call span."""
        sid = hook_input.get("session_id", "")
        tool_use_id = hook_input.get("tool_use_id", "")
        raw_tool_name = hook_input.get("tool_name", "unknown")
        tool_input = hook_input.get("tool_input") or {}
        tool_response = hook_input.get("tool_response")
        started = _tool_started.pop(tool_use_id, _dt.now(UTC))

        # mcp__server__tool_name → server_name="server", tool_name="tool_name"
        # Skip the Claude internal Agent tool — it spawns sub-agents, not an MCP call.
        # Capturing it creates phantom "claude-sdk · Agent" tool_call nodes in the graph.
        if raw_tool_name == "Agent":
            return {"continue_": True}

        server_name = "claude-sdk"
        tool_name = raw_tool_name
        if raw_tool_name.startswith("mcp__"):
            parts = raw_tool_name.split("__", 2)
            if len(parts) >= 2:
                server_name = parts[1]
            if len(parts) == 3:
                tool_name = parts[2]  # just the tool name, not the full mcp__server__tool

        try:
            output_json = (
                _json.dumps(tool_response, default=str) if tool_response is not None else None
            )
        except Exception:  # noqa: BLE001
            output_json = str(tool_response) if tool_response is not None else None

        try:
            span = ToolCallSpan.record(
                server_name=server_name,
                tool_name=tool_name,
                started_at=started,
                status=ToolCallStatus.SUCCESS,
                session_id=sid or None,
                agent_name=_agent_name_for(hook_input),
                span_type="tool_call",
                input_args=tool_input or None,
                output_result=output_json,
                project_id=_project_id(),
                lineage_provenance="explicit",
                schema_version="1.0",
            )
            _global_client.buffer_span(span)
        except Exception:  # noqa: BLE001
            pass
        return {"continue_": True}

    async def _on_post_tool_failure(hook_input: Any, _tid: Any, _ctx: Any) -> Any:
        """Capture tool call failure → tool_call span with error."""
        sid = hook_input.get("session_id", "")
        tool_use_id = hook_input.get("tool_use_id", "")
        tool_name = hook_input.get("tool_name", "unknown")
        error = hook_input.get("error", "unknown error")
        started = _tool_started.pop(tool_use_id, _dt.now(UTC))

        server_name = "claude-sdk"
        if tool_name.startswith("mcp__"):
            parts = tool_name.split("__", 2)
            if len(parts) >= 2:
                server_name = parts[1]

        try:
            span = ToolCallSpan.record(
                server_name=server_name,
                tool_name=tool_name,
                started_at=started,
                status=ToolCallStatus.ERROR,
                error=error,
                session_id=sid or None,
                agent_name=_agent_name_for(hook_input),
                span_type="tool_call",
                project_id=_project_id(),
                lineage_provenance="explicit",
                schema_version="1.0",
            )
            _global_client.buffer_span(span)
        except Exception:  # noqa: BLE001
            pass
        return {"continue_": True}

    async def _on_subagent_start(hook_input: Any, _tid: Any, _ctx: Any) -> Any:
        """Emit handoff span and mark sub-agent as active for this session."""
        sid = hook_input.get("session_id", "")
        agent_type = hook_input.get("agent_type", "unknown")
        started = _dt.now(UTC)

        # Record the active sub-agent BEFORE deriving from_agent so that
        # _agent_name_for uses the PREVIOUS value (the handoff source).
        # from_agent = whoever was active before this sub-agent started.
        from_agent = (
            (sid and _active_subagent.get(sid))  # nested sub-agent case
            or _agent_ctx.get()
            or _os.environ.get("LANGSIGHT_AGENT_NAME")
            or "coordinator"
        )
        # Now mark this sub-agent as active so subsequent tool calls are attributed to it.
        if sid:
            _active_subagent[sid] = agent_type

        try:
            span = ToolCallSpan.record(
                server_name="claude-sdk",
                tool_name=f"→ {agent_type}",
                started_at=started,
                status=ToolCallStatus.SUCCESS,
                session_id=sid or None,
                agent_name=from_agent,
                span_type="handoff",
                target_agent_name=agent_type,
                project_id=_project_id(),
                lineage_provenance="explicit",
                schema_version="1.0",
            )
            _global_client.buffer_span(span)
        except Exception:  # noqa: BLE001
            pass
        return {"continue_": True}

    async def _on_subagent_stop(hook_input: Any, _tid: Any, _ctx: Any) -> Any:
        """Clear sub-agent active state so subsequent calls revert to coordinator."""
        sid = hook_input.get("session_id", "")
        if sid and sid in _active_subagent:
            del _active_subagent[sid]
        return {"continue_": True}

    async def _on_stop(hook_input: Any, _tid: Any, _ctx: Any) -> Any:
        """Emit close-time session span on agent stop."""
        sid = hook_input.get("session_id", "")
        state = _session_state.pop(sid, {})
        started = state.get("started_at", _dt.now(UTC))
        prompt = state.get("prompt")

        # Capture final output — try last_assistant_message first (fastest, no I/O),
        # then fall back to the transcript file which is still present when Stop fires.
        final_output: str | None = None
        last_msg = hook_input.get("last_assistant_message")
        if last_msg:
            # last_assistant_message may be a string (text) or a dict/list of content blocks
            if isinstance(last_msg, str):
                final_output = last_msg
            elif isinstance(last_msg, dict):
                for block in last_msg.get("content", []):
                    if isinstance(block, dict) and block.get("type") == "text":
                        final_output = block.get("text")
                        break
        if not final_output:
            transcript_path = hook_input.get("transcript_path", "")
            if transcript_path:
                try:
                    import json as _jmod

                    lines = open(transcript_path).read().splitlines()  # noqa: ASYNC230,PTH123,SIM115
                    for line in reversed(lines):
                        try:
                            entry = _jmod.loads(line)
                            if entry.get("role") == "assistant":
                                for block in entry.get("content", []):
                                    if isinstance(block, dict) and block.get("type") == "text":
                                        final_output = block["text"]
                                        break
                            if final_output:
                                break
                        except Exception:  # noqa: BLE001
                            continue
                except Exception:  # noqa: BLE001
                    pass

        if prompt or final_output:
            try:
                span = ToolCallSpan.record(
                    server_name="claude-sdk",
                    tool_name="session",
                    started_at=started,
                    status=ToolCallStatus.SUCCESS,
                    session_id=sid or None,
                    agent_name=_agent_name_for(hook_input),
                    span_type="agent",
                    llm_input=prompt,
                    llm_output=final_output,
                    project_id=_project_id(),
                    lineage_provenance="explicit",
                    schema_version="1.0",
                )
                _global_client.buffer_span(span)
                try:
                    await _global_client.flush()
                except Exception:  # noqa: BLE001
                    pass
            except Exception:  # noqa: BLE001
                pass
        return {"continue_": True}

    return {
        "UserPromptSubmit": [HookMatcher(matcher=None, hooks=[_on_user_prompt])],
        "PreToolUse": [HookMatcher(matcher=None, hooks=[_on_pre_tool])],
        "PostToolUse": [HookMatcher(matcher=None, hooks=[_on_post_tool])],
        "PostToolUseFailure": [HookMatcher(matcher=None, hooks=[_on_post_tool_failure])],
        "SubagentStart": [HookMatcher(matcher=None, hooks=[_on_subagent_start])],
        "SubagentStop": [HookMatcher(matcher=None, hooks=[_on_subagent_stop])],
        "Stop": [HookMatcher(matcher=None, hooks=[_on_stop])],
    }


# ---------------------------------------------------------------------------
# LangGraph auto-patch
# ---------------------------------------------------------------------------


def _patch_langgraph() -> None:
    """Inject ``LangSightLangChainCallback`` into LangGraph Pregel methods.

    Patches ``Pregel.stream``, ``Pregel.astream``, ``Pregel.invoke``, and
    ``Pregel.ainvoke`` to auto-inject a LangSight callback into the config.
    The callback captures the full agent tree — agents, tools, LLM calls,
    parent links — with zero user code changes.

    Uses ``_lg_callback_injected`` ContextVar to prevent double-injection when
    ``invoke()`` internally delegates to ``stream()`` (true in all LangGraph
    versions as of 0.2.x).

    Safe to call multiple times (idempotent via ``_patched_sdks``).
    No-op when ``langgraph`` is not installed.
    """
    if "langgraph" in _patched_sdks:
        return

    try:
        from langgraph.pregel import Pregel  # type: ignore[import-not-found]
    except ImportError:
        return

    # --- Helper: extract topology from compiled graph ------------------------

    def _extract_topology(compiled_graph: Any) -> dict[str, Any] | None:
        """Extract graph structure from a CompiledStateGraph's builder."""
        try:
            builder = getattr(compiled_graph, "builder", None)
            if builder is None:
                return None
            nodes = [name for name in (getattr(compiled_graph, "nodes", {}) or {}).keys()]
            edges = []
            for src, tgt in getattr(builder, "edges", set()) or set():
                edges.append({"source": str(src), "target": str(tgt)})
            conditional_edges = []
            branches = getattr(builder, "branches", {}) or {}
            for source_node, branch_dict in branches.items():
                for _branch_name, branch_obj in branch_dict.items():
                    ends = getattr(branch_obj, "ends", None)
                    if ends and isinstance(ends, dict):
                        conditional_edges.append(
                            {
                                "source": str(source_node),
                                "targets": {str(k): str(v) for k, v in ends.items()},
                            }
                        )
                    else:
                        conditional_edges.append(
                            {
                                "source": str(source_node),
                                "targets": {},
                            }
                        )
            entry_point = str(getattr(builder, "entry_point", "__start__") or "__start__")
            return {
                "nodes": nodes,
                "edges": edges,
                "conditional_edges": conditional_edges,
                "entry_point": entry_point,
            }
        except Exception:  # noqa: BLE001
            return None

    # --- Patch StateGraph.compile() to stash topology ------------------------

    def _patch_langgraph_compile() -> None:
        """Patch StateGraph.compile() to stash topology on the compiled graph."""
        try:
            from langgraph.graph.state import StateGraph  # type: ignore[import-not-found]
        except ImportError:
            return
        if hasattr(StateGraph.compile, "_langsight_patched"):
            return
        orig_compile = StateGraph.compile
        _originals["langgraph_compile"] = orig_compile

        def _patched_compile(self_graph: Any, *args: Any, **kwargs: Any) -> Any:
            compiled = orig_compile(self_graph, *args, **kwargs)
            topology = _extract_topology(compiled)
            if topology is not None:
                try:
                    object.__setattr__(compiled, "_langsight_topology", topology)
                except (TypeError, AttributeError):
                    compiled._langsight_topology = topology
            return compiled

        _patched_compile._langsight_patched = True  # type: ignore[attr-defined]
        StateGraph.compile = _patched_compile

    _patch_langgraph_compile()

    # --- Helper: emit topology span ------------------------------------------

    def _emit_topology_span(
        topology: dict[str, Any],
        session_id: str | None,
        trace_id: str | None,
        agent_name: str | None,
    ) -> None:
        """Emit a span_type='topology' span with graph structure."""
        client = _resolve_client()
        if client is None:
            return
        try:
            from langsight.sdk.models import ToolCallSpan, ToolCallStatus

            span = ToolCallSpan.record(
                server_name="langgraph",
                tool_name="graph_topology",
                started_at=datetime.now(UTC),
                status=ToolCallStatus.SUCCESS,
                session_id=session_id,
                trace_id=trace_id,
                agent_name=agent_name,
                span_type="topology",
                input_args=topology,
                project_id=getattr(client, "_project_id", None) or "",
            )
            client.buffer_span(span)
        except Exception:  # noqa: BLE001
            pass

    # --- Helper: build a fresh callback for the current context -------------

    def _make_lg_callback() -> Any | None:
        """Create a ``LangSightLangChainCallback`` for the current context."""
        client = _resolve_client()
        if client is None:
            return None
        try:
            from langsight.integrations.langchain import LangSightLangChainCallback
        except ImportError:
            return None

        # Tier 2: Create per-run budget if client has budget config
        budget = None
        if getattr(client, "_budget_config", None) is not None:
            from langsight.sdk.budget import SessionBudget

            budget = SessionBudget(client._budget_config)

        return LangSightLangChainCallback(
            client=client,
            server_name=None,  # auto-detect mode
            agent_name=_agent_ctx.get() or None,
            session_id=_session_ctx.get() or None,
            trace_id=_trace_ctx.get() or None,
            max_node_iterations=getattr(client, "_max_node_iterations", 10),
            budget=budget,
            pricing_table=getattr(client, "_pricing_table", None),
        )

    # --- Helper: inject callback into config --------------------------------

    def _inject_callback(
        config: dict[str, Any] | None,
        self_graph: Any = None,
    ) -> tuple[dict[str, Any] | None, Any | None]:
        """Return ``(new_config, callback)`` with our callback prepended.

        Returns ``(original_config, None)`` when injection is not needed:
        no client, already injected, or user already added our callback.
        """
        if _lg_callback_injected.get():
            return config, None

        # Check if user already provided a LangSight callback
        if config is not None:
            existing = config.get("callbacks")
            if isinstance(existing, list):
                try:
                    from langsight.integrations.langchain import (
                        LangSightLangChainCallback,
                    )

                    if any(isinstance(cb, LangSightLangChainCallback) for cb in existing):
                        return config, None
                except ImportError:
                    pass

        cb = _make_lg_callback()
        if cb is None:
            return config, None

        # Emit topology span if graph has it
        if self_graph is not None:
            topo = getattr(self_graph, "_langsight_topology", None)
            if topo is not None:
                _emit_topology_span(
                    topo,
                    session_id=_session_ctx.get() or None,
                    trace_id=_trace_ctx.get() or None,
                    agent_name=_agent_ctx.get() or None,
                )
                # Only emit once per graph instance
                try:
                    object.__setattr__(self_graph, "_langsight_topology", None)
                except (TypeError, AttributeError):
                    self_graph._langsight_topology = None

        # Build config with our callback prepended
        if config is None:
            return {"callbacks": [cb]}, cb

        new_config = dict(config)  # shallow copy — don't mutate caller's dict
        existing_cbs = new_config.get("callbacks")
        if existing_cbs is None:
            new_config["callbacks"] = [cb]
        elif isinstance(existing_cbs, list):
            new_config["callbacks"] = [cb, *existing_cbs]
        else:
            # existing_cbs is a CallbackManager — try merge_configs
            try:
                from langchain_core.runnables.config import merge_configs

                new_config = merge_configs(new_config, {"callbacks": [cb]})
            except ImportError:
                new_config["callbacks"] = [cb]

        return new_config, cb

    # --- Helper: flush after graph execution --------------------------------

    def _try_flush_lg() -> None:
        """Best-effort sync flush of buffered spans."""
        client = _resolve_client()
        if client is None:
            return
        try:
            loop = asyncio.get_running_loop()
            if not loop.is_closed():
                loop.create_task(client.flush())
        except RuntimeError:
            # No running event loop — try blocking flush
            try:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(client.flush())
                loop.close()
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass

    async def _try_flush_lg_async() -> None:
        """Best-effort async flush of buffered spans."""
        client = _resolve_client()
        if client is None:
            return
        try:
            await client.flush()
        except Exception:  # noqa: BLE001
            pass

    # ── Patch stream() ─────────────────────────────────────────────────────

    orig_stream = Pregel.stream
    _originals["langgraph_stream"] = orig_stream

    def _patched_stream(
        self_graph: Any,
        input: Any,  # noqa: A002
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        new_config, cb = _inject_callback(config, self_graph=self_graph)
        if cb is None:
            yield from orig_stream(self_graph, input, new_config, **kwargs)
            return

        token = _lg_callback_injected.set(True)
        try:
            yield from orig_stream(self_graph, input, new_config, **kwargs)
        finally:
            _lg_callback_injected.reset(token)
            _try_flush_lg()

    Pregel.stream = _patched_stream

    # ── Patch astream() ────────────────────────────────────────────────────

    orig_astream = Pregel.astream
    _originals["langgraph_astream"] = orig_astream

    async def _patched_astream(
        self_graph: Any,
        input: Any,  # noqa: A002
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        new_config, cb = _inject_callback(config, self_graph=self_graph)
        if cb is None:
            async for chunk in orig_astream(self_graph, input, new_config, **kwargs):
                yield chunk
            return

        token = _lg_callback_injected.set(True)
        try:
            async for chunk in orig_astream(self_graph, input, new_config, **kwargs):
                yield chunk
        finally:
            _lg_callback_injected.reset(token)
            await _try_flush_lg_async()

    Pregel.astream = _patched_astream

    # ── Patch invoke() ─────────────────────────────────────────────────────

    orig_invoke = Pregel.invoke
    _originals["langgraph_invoke"] = orig_invoke

    def _patched_invoke(
        self_graph: Any,
        input: Any,  # noqa: A002
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        new_config, cb = _inject_callback(config, self_graph=self_graph)
        if cb is None:
            return orig_invoke(self_graph, input, new_config, **kwargs)

        token = _lg_callback_injected.set(True)
        try:
            return orig_invoke(self_graph, input, new_config, **kwargs)
        finally:
            _lg_callback_injected.reset(token)
            _try_flush_lg()

    Pregel.invoke = _patched_invoke

    # ── Patch ainvoke() ────────────────────────────────────────────────────

    orig_ainvoke = Pregel.ainvoke
    _originals["langgraph_ainvoke"] = orig_ainvoke

    async def _patched_ainvoke(
        self_graph: Any,
        input: Any,  # noqa: A002
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        new_config, cb = _inject_callback(config, self_graph=self_graph)
        if cb is None:
            return await orig_ainvoke(self_graph, input, new_config, **kwargs)

        token = _lg_callback_injected.set(True)
        try:
            return await orig_ainvoke(self_graph, input, new_config, **kwargs)
        finally:
            _lg_callback_injected.reset(token)
            await _try_flush_lg_async()

    Pregel.ainvoke = _patched_ainvoke

    _patched_sdks.add("langgraph")
    logger.debug("auto_patch.patched", sdk="langgraph")


def auto_patch(
    url: str | None = None,
    api_key: str | None = None,
    project_id: str | None = None,
    agent_name: str | None = None,
    **kwargs: Any,
) -> Any | None:
    """Monkey-patch all known LLM SDKs and MCP for zero-code auto-tracing.

    v0.12.0 patches:
    - ``openai``, ``anthropic``, ``google.genai``, ``google.generativeai``
      (LLM generation calls — any client created after this is auto-traced)
    - ``mcp.ClientSession.call_tool`` (every MCP tool call auto-traced)

    After this call, inside a :func:`session` block you need zero additional
    instrumentation — no ``wrap_llm()``, no ``wrap()``, no ``create_handoff()``::

        import langsight
        langsight.auto_patch()  # call once at startup

        async with langsight.session(agent_name="orchestrator") as session_id:
            client = OpenAI()                          # LLM: auto-traced
            result = await mcp_session.call_tool(...)  # MCP: auto-traced
            # LLM tool named "call_analyst" → handoff span: auto-emitted

    **MCP auto-patch**: ``_patch_mcp()`` monkey-patches
    ``mcp.ClientSession.call_tool``. Every tool call is attributed to the
    agent, session, and trace from the active :func:`session` context. The
    server name is read from the MCP session's ``_server_info.name`` attribute
    when available, falling back to ``"mcp"``.

    **Handoff auto-detection**: after each LLM generation, tool names matching
    ``call_*``, ``delegate_*``, ``invoke_*``, ``transfer_to_*``, ``run_*``, or
    ``dispatch_*`` trigger an automatic handoff span from the current agent to
    the target. No ``create_handoff()`` call is needed.

    Reads ``LANGSIGHT_URL``, ``LANGSIGHT_API_KEY``, and
    ``LANGSIGHT_PROJECT_ID`` from the environment (explicit args take priority).
    Returns ``None`` if ``LANGSIGHT_URL`` is not set — safe to call
    unconditionally (observability optional by design).

    Args:
        url: LangSight server URL (or ``LANGSIGHT_URL`` env var).
        api_key: API key (or ``LANGSIGHT_API_KEY`` env var).
        project_id: Project ID (or ``LANGSIGHT_PROJECT_ID`` env var).
        agent_name: Default agent name for all auto-patched spans. Sets
            ``_agent_ctx`` so wrap() / wrap_llm() inherit it automatically.
        **kwargs: Forwarded to :class:`LangSightClient` (e.g.
            ``loop_detection=True``, ``max_steps=25``).

    Returns:
        The :class:`LangSightClient` instance, or ``None`` if URL not set.
    """
    import os

    from langsight.sdk import init  # lazy to avoid circular

    global _global_client, _deferred_init

    resolved_agent = agent_name or os.environ.get("LANGSIGHT_AGENT_NAME")
    if resolved_agent:
        _agent_ctx.set(resolved_agent)

    # Auto-load .env if LANGSIGHT_URL is not set — covers the common pattern where
    # users call auto_patch() at module import time, before load_dotenv().
    # Same approach used by AgentOps and Langfuse integrations.
    if not (url or os.environ.get("LANGSIGHT_URL")):
        try:
            from dotenv import load_dotenv as _ld

            _ld()
        except ImportError:
            pass  # python-dotenv not installed — env vars must be set explicitly

    ls = init(url=url, api_key=api_key, project_id=project_id, **kwargs)
    if ls is None:
        # Still no URL after dotenv attempt — store for lazy retry on first span.
        _deferred_init = {"url": url, "api_key": api_key, "project_id": project_id, **kwargs}
        logger.info(
            "auto_patch.deferred",
            message=(
                "LANGSIGHT_URL not set — patches active, spans sent when URL becomes available."
            ),
        )
        # Fall through — install all patches so they fire when spans arrive

    _global_client = ls

    _patch_openai()
    _patch_anthropic()
    _patch_google_genai()
    _patch_google_generativeai()
    _patch_mcp()
    _patch_claude_sdk()
    _patch_crewai()
    _patch_langgraph()

    logger.info(
        "auto_patch.complete",
        patched=sorted(_patched_sdks),
        skipped_missing=[
            sdk
            for sdk in [
                "openai",
                "anthropic",
                "google_genai",
                "google_generativeai",
                "mcp",
                "claude_sdk",
                "crewai",
                "langgraph",
            ]
            if sdk not in _patched_sdks
        ],
    )
    return ls


def _patch_mcp() -> None:
    """Patch mcp.ClientSession.call_tool for zero-config MCP tracing.

    Called automatically by :func:`auto_patch` (v0.12.0). After patching,
    every ``await mcp_session.call_tool(name, args)`` is automatically traced
    with the ``agent_name``, ``session_id``, and ``trace_id`` from the active
    :func:`session` context — no ``ls.wrap()`` required.

    Server name resolution order:
    1. ``session._server_info.name`` (set by MCP handshake)
    2. ``session._server_name`` (manually set attribute)
    3. Falls back to ``"mcp"``

    If an ``llm_intent`` span is pending for this tool name (i.e. the LLM
    just decided to call this tool), the MCP span claims it as its parent,
    creating a complete intent → execution link in the trace.

    The original method is stored in ``_originals["mcp_call_tool"]`` and
    restored by :func:`unpatch`. Safe to call multiple times — no-op if
    ``mcp`` is already in ``_patched_sdks``. Returns immediately if the
    ``mcp`` package is not installed.
    """
    try:
        from mcp import ClientSession
    except ImportError:
        return  # MCP not installed — skip silently

    if "mcp" in _patched_sdks:
        return  # already patched

    orig_call_tool = ClientSession.call_tool
    _originals["mcp_call_tool"] = orig_call_tool

    async def _patched_call_tool(
        self_sdk: Any,
        name: str,
        arguments: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        if _global_client is None:
            return await orig_call_tool(self_sdk, name, arguments, **kwargs)

        # MCPClientProxy already traced this call — skip auto_patch to prevent
        # double-tracing when explicit ls.wrap() and auto_patch() are both active.
        if _mcp_proxy_active.get():
            return await orig_call_tool(self_sdk, name, arguments, **kwargs)

        from langsight.sdk.context import claim_pending_tool
        from langsight.sdk.models import ToolCallSpan, ToolCallStatus

        agent_name = _agent_ctx.get() or None
        session_id = _session_ctx.get() or None
        trace_id = _trace_ctx.get() or None

        # Claim llm_intent parent span if LLM decided to call this tool
        pending = claim_pending_tool(name)
        parent_span_id = pending.span_id if pending else None
        if pending and not agent_name:
            agent_name = pending.agent_name

        # Derive server_name from MCP session's server info if available
        server_info = getattr(self_sdk, "_server_info", None)
        server_name = (
            getattr(server_info, "name", None)
            if server_info
            else getattr(self_sdk, "_server_name", None)
        ) or "mcp"

        started_at = datetime.now(UTC)
        status = ToolCallStatus.SUCCESS
        error: str | None = None
        result: Any = None
        try:
            result = await orig_call_tool(self_sdk, name, arguments, **kwargs)
            return result
        except TimeoutError as exc:
            status = ToolCallStatus.TIMEOUT
            error = f"TimeoutError: {exc}"
            raise
        except BaseException as exc:  # noqa: BLE001
            status = ToolCallStatus.ERROR
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            span = ToolCallSpan.record(
                server_name=server_name,
                tool_name=name,
                started_at=started_at,
                status=status,
                error=error,
                agent_name=agent_name,
                session_id=session_id,
                trace_id=trace_id,
                parent_span_id=parent_span_id,
                input_args=arguments,
                output_result=str(result) if result is not None else None,
                lineage_provenance="explicit",
                schema_version="1.0",
            )
            _global_client.buffer_span(span)

    ClientSession.call_tool = _patched_call_tool  # type: ignore[method-assign, assignment]
    _patched_sdks.add("mcp")
    logger.debug("auto_patch.patched", sdk="mcp")


def unpatch() -> None:
    """Restore all original SDK methods (useful for testing)."""
    global _global_client

    try:
        from openai.resources.chat.completions import AsyncCompletions, Completions

        if "openai_sync" in _originals:
            Completions.create = _originals.pop("openai_sync")  # type: ignore[method-assign]
        if "openai_async" in _originals:
            AsyncCompletions.create = _originals.pop("openai_async")  # type: ignore[method-assign]
    except (ImportError, AttributeError):
        pass

    try:
        from anthropic.resources.messages import AsyncMessages, Messages

        if "anthropic_sync" in _originals:
            Messages.create = _originals.pop("anthropic_sync")  # type: ignore[method-assign]
        if "anthropic_async" in _originals:
            AsyncMessages.create = _originals.pop("anthropic_async")  # type: ignore[method-assign]
    except (ImportError, AttributeError):
        pass

    try:
        from google.genai import models as _genai_models

        if "genai_sync" in _originals:
            _genai_models.Models.generate_content = _originals.pop("genai_sync")
        if "genai_async" in _originals:
            _genai_models.AsyncModels.generate_content = _originals.pop("genai_async")
    except (ImportError, AttributeError):
        pass

    try:
        from google.generativeai.generative_models import GenerativeModel

        if "genai_legacy_sync" in _originals:
            GenerativeModel.generate_content = _originals.pop("genai_legacy_sync")
        if "genai_legacy_async" in _originals:
            GenerativeModel.generate_content_async = _originals.pop("genai_legacy_async")
    except (ImportError, AttributeError):
        pass

    try:
        from mcp import ClientSession

        if "mcp_call_tool" in _originals:
            ClientSession.call_tool = _originals.pop("mcp_call_tool")  # type: ignore[method-assign]
    except (ImportError, AttributeError):
        pass

    try:
        import crewai as _crewai_mod

        if "crewai_crew_init" in _originals:
            _crewai_mod.Crew.__init__ = _originals.pop("crewai_crew_init")
        if "crewai_agent_init" in _originals:
            _crewai_mod.Agent.__init__ = _originals.pop("crewai_agent_init")
        if "crewai_kickoff" in _originals:
            _crewai_mod.Crew.kickoff = _originals.pop("crewai_kickoff")
        if "crewai_base_tool_run" in _originals:
            try:
                from crewai.tools.base_tool import BaseTool as _BT

                _BT.run = _originals.pop("crewai_base_tool_run")
            except ImportError:
                _originals.pop("crewai_base_tool_run", None)
        if "crewai_agent_kickoff" in _originals:
            try:
                from crewai.agent.core import Agent as _CAC

                _CAC.kickoff = _originals.pop("crewai_agent_kickoff")
            except ImportError:
                _originals.pop("crewai_agent_kickoff", None)
    except (ImportError, AttributeError):
        pass

    try:
        from langgraph.pregel import Pregel

        if "langgraph_stream" in _originals:
            Pregel.stream = _originals.pop("langgraph_stream")
        if "langgraph_astream" in _originals:
            Pregel.astream = _originals.pop("langgraph_astream")
        if "langgraph_invoke" in _originals:
            Pregel.invoke = _originals.pop("langgraph_invoke")
        if "langgraph_ainvoke" in _originals:
            Pregel.ainvoke = _originals.pop("langgraph_ainvoke")
    except (ImportError, AttributeError):
        pass

    try:
        from langgraph.graph.state import StateGraph

        if "langgraph_compile" in _originals:
            StateGraph.compile = _originals.pop("langgraph_compile")
    except (ImportError, AttributeError):
        pass

    _patched_sdks.clear()
    _global_client = None
    logger.debug("auto_patch.unpatched")


def set_context(
    session_id: str | None = None,
    agent_name: str | None = None,
    trace_id: str | None = None,
) -> list[contextvars.Token[str | None]]:
    """Set tracing context for the current async task or thread.

    Returns a list of tokens that can be passed to :func:`clear_context`
    to restore the previous values::

        tokens = langsight.set_context(session_id="sess-001", agent_name="analyst")
        # ... agent runs ...
        langsight.clear_context(tokens)
    """
    tokens: list[contextvars.Token[str | None]] = []
    if session_id is not None:
        tokens.append(_session_ctx.set(session_id))
    if agent_name is not None:
        tokens.append(_agent_ctx.set(agent_name))
    if trace_id is not None:
        tokens.append(_trace_ctx.set(trace_id))
    return tokens


def clear_context(tokens: list[contextvars.Token[str | None]]) -> None:
    """Restore context variables to their values before :func:`set_context`."""
    for token in tokens:
        token.var.reset(token)


class SessionContext(str):
    """Returned by :func:`session`. Subclasses ``str`` for backward compatibility.

    Existing code that treats the yielded value as a plain session_id string
    continues to work. New code can use the additional methods to capture
    the human prompt, final response, and mid-session user messages.

    Example::

        async with langsight.session(
            agent_name="orchestrator",
            input="What products need restocking?",
        ) as sess:
            result = await agent.run(question)
            sess.set_output(result)                      # capture final answer

        # Human-in-the-loop / clarification mid-session:
        async with langsight.session(agent_name="orchestrator") as sess:
            partial = await agent.analyze(question)
            approval = await ask_human("Place order for 50 units?")
            sess.record_user_message(approval)           # first-class HITL span
            result = await agent.execute(approval)
            sess.set_output(result)
    """

    def __new__(
        cls,
        session_id: str,
        agent_name: str | None = None,
        trace_id: str | None = None,
        started_at: datetime | None = None,
        input_text: str | None = None,
    ) -> SessionContext:
        return str.__new__(cls, session_id)

    def __init__(
        self,
        session_id: str,
        agent_name: str | None = None,
        trace_id: str | None = None,
        started_at: datetime | None = None,
        input_text: str | None = None,
    ) -> None:
        super().__init__()
        object.__setattr__(self, "_agent_name", agent_name)
        object.__setattr__(self, "_trace_id", trace_id)
        object.__setattr__(self, "_started_at", started_at or datetime.now(UTC))
        object.__setattr__(self, "_input_text", input_text)
        object.__setattr__(self, "_output_text", None)
        object.__setattr__(self, "_usage", None)
        object.__setattr__(self, "_session_id", session_id)

    def set_output(self, output: str) -> None:
        """Capture the final agent response for display in the dashboard.

        Call this at the end of the agent run with the final answer::

            async with langsight.session(input=question) as sess:
                result = await agent.run(question)
                sess.set_output(result)
        """
        object.__setattr__(self, "_output_text", str(output))

    def set_usage(
        self,
        *,
        cost_usd: float | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cache_read_tokens: int | None = None,
        cache_creation_tokens: int | None = None,
        model_id: str | None = None,
    ) -> None:
        """Record token usage and cost for the session.

        Call this when you receive a ``ResultMessage`` from the Claude Agent SDK::

            async with langsight.session(agent_name="coordinator") as sess:
                async for msg in query(prompt=prompt, options=options):
                    if isinstance(msg, ResultMessage):
                        usage = msg.usage or {}
                        sess.set_usage(
                            cost_usd=msg.total_cost_usd,
                            input_tokens=usage.get("input_tokens"),
                            output_tokens=usage.get("output_tokens"),
                            cache_read_tokens=usage.get("cache_read_input_tokens"),
                            cache_creation_tokens=usage.get("cache_creation_input_tokens"),
                        )
        """
        object.__setattr__(
            self,
            "_usage",
            {
                "cost_usd": cost_usd,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_tokens": cache_read_tokens,
                "cache_creation_tokens": cache_creation_tokens,
                "model_id": model_id,
            },
        )

    def record_user_message(self, text: str) -> None:
        """Record a human message mid-session — HITL, clarification, approval.

        Creates a ``user_message`` span in the session timeline so the
        dashboard shows exactly when the human intervened and what they said::

            async with langsight.session(agent_name="orchestrator") as sess:
                partial = await agent.first_pass(question)
                approval = await ask_human("Confirm order for 50 units?")
                sess.record_user_message(approval)
                result = await agent.finalize(approval)
        """
        if _global_client is None:
            return
        from langsight.sdk.models import ToolCallSpan, ToolCallStatus

        span = ToolCallSpan.record(
            server_name="human",
            tool_name=text[:120] if len(text) > 120 else text,  # truncated label
            started_at=datetime.now(UTC),
            status=ToolCallStatus.SUCCESS,
            agent_name=object.__getattribute__(self, "_agent_name"),
            session_id=object.__getattribute__(self, "_session_id"),
            trace_id=object.__getattribute__(self, "_trace_id"),
            span_type="user_message",
            llm_input=text,  # full message stored here
            lineage_provenance="explicit",
            schema_version="1.0",
        )
        _global_client.buffer_span(span)


@contextlib.asynccontextmanager
async def session(
    agent_name: str | None = None,
    trace_id: str | None = None,
    session_id: str | None = None,
    input: str | None = None,  # noqa: A002 — mirrors LangSmith/Langfuse API convention
) -> Any:
    """Async context manager that sets a tracing context for an agent run.

    Generates a ``session_id`` if not provided.  All LLM + MCP calls inside
    the block are tagged with this session automatically.

    v0.13.0 additions:
    - ``input``: capture the human prompt that started this session
    - Yields a :class:`SessionContext` (backward-compatible with plain str)
    - ``sess.set_output(result)``: capture the final agent response
    - ``sess.record_user_message(text)``: record mid-session human input

    Examples::

        # Simple — just set context:
        async with langsight.session(agent_name="orchestrator") as session_id:
            response = await client.aio.models.generate_content(...)

        # With input/output capture:
        async with langsight.session(
            agent_name="orchestrator",
            input="What products need restocking?",
        ) as sess:
            result = await agent.run(question)
            sess.set_output(result)

        # Multi-turn conversation (same trace_id links sessions):
        async with langsight.session(
            agent_name="orchestrator",
            input=turn1,
            trace_id=conversation_id,
        ) as sess:
            result = await agent.run(turn1)
            sess.set_output(result)
    """
    sid = session_id or str(uuid.uuid4())
    started_at = datetime.now(UTC)
    ctx = SessionContext(
        sid,
        agent_name=agent_name,
        trace_id=trace_id,
        started_at=started_at,
        input_text=input,
    )
    tokens = set_context(session_id=sid, agent_name=agent_name, trace_id=trace_id)

    try:
        # Emit the session_start span immediately so the prompt is persisted before
        # the agent runs — matches Langfuse/LangSmith behaviour where input is written
        # at trace-open time, not at close. This means even if the agent crashes or
        # set_output() is never called, the human prompt is already in ClickHouse.
        if input is not None and _global_client is not None:
            from langsight.sdk.models import ToolCallSpan, ToolCallStatus

            _proj = getattr(_global_client, "_project_id", None) or None
            try:
                start_span = ToolCallSpan.record(
                    server_name=agent_name or "agent",
                    tool_name="session",
                    started_at=started_at,
                    status=ToolCallStatus.SUCCESS,
                    agent_name=agent_name,
                    session_id=sid,
                    trace_id=trace_id,
                    span_type="agent",
                    llm_input=input,
                    llm_output=None,  # output not known yet
                    project_id=_proj,
                    lineage_provenance="explicit",
                    schema_version="1.0",
                )
                # Post directly — do NOT buffer_span + flush() here.
                # flush() drains the entire shared buffer, racing with _flush_loop.
                await _global_client._post_spans([start_span])
            except Exception:  # noqa: BLE001
                pass  # fail-open — if post fails, prompt is lost but agent still runs

        yield ctx
    finally:
        clear_context(tokens)
        # Emit a close-time span when output was captured via set_output().
        # This span carries both llm_input and llm_output so the detail page
        # can show the complete prompt→answer pair.
        # If only input was provided (no set_output call), the start span
        # emitted above already has the prompt — no duplicate needed.
        _input = object.__getattribute__(ctx, "_input_text")
        _output = object.__getattribute__(ctx, "_output_text")
        if _output is not None and _global_client is not None:
            from langsight.sdk.models import ToolCallSpan, ToolCallStatus

            _proj = getattr(_global_client, "_project_id", None) or None
            root_span = ToolCallSpan.record(
                server_name=agent_name or "agent",
                tool_name="session",
                started_at=started_at,  # session wall-clock duration
                status=ToolCallStatus.SUCCESS,
                agent_name=agent_name,
                session_id=sid,
                trace_id=trace_id,
                span_type="agent",
                llm_input=_input,
                llm_output=_output,
                project_id=_proj,
                lineage_provenance="explicit",
                schema_version="1.0",
            )
            _global_client.buffer_span(root_span)
        elif _input is None and _output is None:
            # No input or output at all — nothing to emit (keep previous behaviour
            # of not cluttering ClickHouse with empty session spans).
            pass

        # Emit token usage span if set_usage() was called
        _usage = object.__getattribute__(ctx, "_usage")
        if _usage and _global_client is not None:
            try:
                import json as _j2

                from langsight.sdk.models import ToolCallSpan, ToolCallStatus

                _proj = getattr(_global_client, "_project_id", None) or None
                _cost = _usage.get("cost_usd")
                usage_span = ToolCallSpan.record(
                    server_name="claude-sdk",
                    tool_name="usage",
                    started_at=started_at,
                    status=ToolCallStatus.SUCCESS,
                    agent_name=agent_name or "coordinator",
                    session_id=sid,
                    trace_id=trace_id,
                    span_type="agent",
                    input_tokens=_usage.get("input_tokens"),
                    output_tokens=_usage.get("output_tokens"),
                    cache_read_tokens=_usage.get("cache_read_tokens"),
                    cache_creation_tokens=_usage.get("cache_creation_tokens"),
                    model_id=_usage.get("model_id") or "",
                    output_result=_j2.dumps({"cost_usd": _cost}) if _cost is not None else None,
                    project_id=_proj,
                    lineage_provenance="explicit",
                    schema_version="1.0",
                )
                _global_client.buffer_span(usage_span)
            except Exception:  # noqa: BLE001
                pass

        if _global_client is not None:
            try:
                await _global_client.flush()
            except Exception:  # noqa: BLE001
                pass  # fail-open — flush is best-effort
