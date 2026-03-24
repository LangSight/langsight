"""
Monkey-patch auto-instrumentation — patches LLM SDK classes at import time.

After calling ``auto_patch()``, every LLM client you create is automatically
traced — no explicit ``wrap_llm()`` call needed.

Usage (minimal)::

    import langsight
    langsight.auto_patch()          # reads LANGSIGHT_* env vars

    from openai import OpenAI
    client = OpenAI()               # automatically traced — no wrap_llm() needed
    response = client.chat.completions.create(model="gpt-4o", ...)

Usage (with context)::

    import langsight

    langsight.auto_patch()

    async def run_agent(question: str) -> str:
        async with langsight.session(agent_name="analyst") as session_id:
            client = genai.Client()
            response = await client.aio.models.generate_content(...)
            # All LLM calls inside this block share the same session_id
        return response.text

Supported SDKs (all optional — missing SDKs are skipped):
  - openai  (OpenAI, AsyncOpenAI)
  - anthropic  (Anthropic, AsyncAnthropic)
  - google.genai  (new SDK: google-genai)
  - google.generativeai  (legacy SDK: google-generativeai)
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

# ---------------------------------------------------------------------------
# Module-level state — patched SDK originals + global client
# ---------------------------------------------------------------------------

_originals: dict[str, Any] = {}          # original SDK methods, keyed by SDK name
_patched_sdks: set[str] = set()          # set of patched SDK names
_global_client: Any | None = None        # LangSightClient singleton (avoids circular import)


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
    ) -> None:
        object.__setattr__(self, "_langsight", ls)
        object.__setattr__(self, "_agent_name", agent_name)
        object.__setattr__(self, "_session_id", session_id)
        object.__setattr__(self, "_trace_id", trace_id)
        object.__setattr__(self, "_redact", getattr(ls, "_redact_payloads", False))
        object.__setattr__(self, "_project_id", getattr(ls, "_project_id", None) or "")
        # _client not needed — model name comes via model_override or response

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
                _process_openai_response(proxy, response, kwargs, started_at, status=status, error=error)

        Completions.create = _patched_sync  # type: ignore[method-assign]
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
                _process_openai_response(proxy, response, kwargs, started_at, status=status, error=error)

        AsyncCompletions.create = _patched_async  # type: ignore[method-assign]
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
                _process_anthropic_response(proxy, response, kwargs, started_at, status=status, error=error)

        Messages.create = _patched_sync  # type: ignore[method-assign]
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
                _process_anthropic_response(proxy, response, kwargs, started_at, status=status, error=error)

        AsyncMessages.create = _patched_async  # type: ignore[method-assign]
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
                _process_gemini_response(proxy, response, kwargs, started_at, model_override=model, status=status, error=error)

        _genai_models.Models.generate_content = _patched_sync  # type: ignore[method-assign]
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
                _process_gemini_response(proxy, response, kwargs, started_at, model_override=model, status=status, error=error)

        _genai_models.AsyncModels.generate_content = _patched_async  # type: ignore[method-assign]
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
                _process_gemini_response(proxy, response, kwargs, started_at, status=status, error=error)

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
                _process_gemini_response(proxy, response, kwargs, started_at, status=status, error=error)

        GenerativeModel.generate_content = _patched_sync  # type: ignore[method-assign]
        GenerativeModel.generate_content_async = _patched_async  # type: ignore[method-assign]
    except (ImportError, AttributeError):
        pass

    _patched_sdks.add("google_generativeai")
    logger.debug("auto_patch.patched", sdk="google.generativeai")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def auto_patch(
    url: str | None = None,
    api_key: str | None = None,
    project_id: str | None = None,
    agent_name: str | None = None,
    **kwargs: Any,
) -> Any | None:
    """Monkey-patch all known LLM SDK classes for zero-code auto-tracing.

    Patches ``openai``, ``anthropic``, ``google.genai``, and
    ``google.generativeai`` at the class level.  Any LLM client you create
    after calling this is automatically traced — no ``wrap_llm()`` needed.

    Reads ``LANGSIGHT_URL``, ``LANGSIGHT_API_KEY``, and
    ``LANGSIGHT_PROJECT_ID`` from the environment (explicit args take priority).
    Returns ``None`` if ``LANGSIGHT_URL`` is not set.

    Pass per-call context via :func:`set_context` or the :func:`session`
    async context manager::

        async with langsight.session(agent_name="analyst") as sid:
            response = await client.aio.models.generate_content(...)

    Args:
        url: LangSight server URL (or ``LANGSIGHT_URL`` env var).
        api_key: API key (or ``LANGSIGHT_API_KEY`` env var).
        project_id: Project ID (or ``LANGSIGHT_PROJECT_ID`` env var).
        agent_name: Default agent name for all auto-patched spans.
        **kwargs: Forwarded to :class:`LangSightClient` (e.g. ``loop_detection=True``).

    Returns:
        The :class:`LangSightClient` instance, or ``None`` if URL not set.
    """
    import os

    from langsight.sdk import init  # lazy to avoid circular

    global _global_client

    resolved_agent = agent_name or os.environ.get("LANGSIGHT_AGENT_NAME")
    if resolved_agent:
        _agent_ctx.set(resolved_agent)

    ls = init(url=url, api_key=api_key, project_id=project_id, **kwargs)
    if ls is None:
        return None

    _global_client = ls

    _patch_openai()
    _patch_anthropic()
    _patch_google_genai()
    _patch_google_generativeai()

    logger.info(
        "auto_patch.complete",
        patched=sorted(_patched_sdks),
        skipped_missing=[
            sdk for sdk in ["openai", "anthropic", "google_genai", "google_generativeai"]
            if sdk not in _patched_sdks
        ],
    )
    return ls


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
            _genai_models.Models.generate_content = _originals.pop("genai_sync")  # type: ignore[method-assign]
        if "genai_async" in _originals:
            _genai_models.AsyncModels.generate_content = _originals.pop("genai_async")  # type: ignore[method-assign]
    except (ImportError, AttributeError):
        pass

    try:
        from google.generativeai.generative_models import GenerativeModel
        if "genai_legacy_sync" in _originals:
            GenerativeModel.generate_content = _originals.pop("genai_legacy_sync")  # type: ignore[method-assign]
        if "genai_legacy_async" in _originals:
            GenerativeModel.generate_content_async = _originals.pop("genai_legacy_async")  # type: ignore[method-assign]
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


@contextlib.asynccontextmanager
async def session(
    agent_name: str | None = None,
    trace_id: str | None = None,
    session_id: str | None = None,
):  # type: ignore[return]
    """Async context manager that sets a tracing context for an agent run.

    Generates a ``session_id`` if not provided.  All LLM calls inside the
    block are tagged with this session::

        async with langsight.session(agent_name="orchestrator") as session_id:
            response = await client.aio.models.generate_content(...)
            print(f"Session: {session_id}")
    """
    sid = session_id or str(uuid.uuid4())
    tokens = set_context(session_id=sid, agent_name=agent_name, trace_id=trace_id)
    try:
        yield sid
    finally:
        clear_context(tokens)
        if _global_client is not None:
            try:
                await _global_client.flush()
            except Exception:  # noqa: BLE001
                pass  # fail-open — flush is best-effort
