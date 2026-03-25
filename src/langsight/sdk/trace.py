"""
Agent tracing decorator and context manager.

Captures the full lifecycle of an agent function — start, output, and any
exception raised between LLM calls (not just inside them).  Follows the
Langfuse ``@observe`` / LangWatch ``with trace()`` patterns.

Usage (decorator)::

    @langsight.trace(agent_name="orchestrator")
    async def run(question: str) -> str:
        response = await client.aio.models.generate_content(...)
        ...

Usage (context manager)::

    async with langsight.trace(agent_name="analyst") as t:
        result = await analyst.analyze(question)
        t.set_output(result)   # optional — record the final answer

Usage (manual with explicit client)::

    @langsight.trace(client=ls, agent_name="orchestrator", session_id="sess-001")
    async def run(question: str) -> str:
        ...
"""

from __future__ import annotations

import asyncio
import functools
import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any, TypeVar

import structlog

from langsight.sdk.models import ToolCallSpan, ToolCallStatus

logger = structlog.get_logger()

F = TypeVar("F", bound=Callable[..., Coroutine[Any, Any, Any]])


class AgentTrace:
    """Active agent trace — records start, captures exceptions, records end.

    Returned by :func:`trace` when used as a context manager.
    """

    def __init__(
        self,
        client: Any,  # LangSightClient
        agent_name: str | None,
        session_id: str | None,
        trace_id: str | None,
        project_id: str | None,
    ) -> None:
        self._client = client
        self._agent_name = agent_name
        self._session_id = session_id
        self._trace_id = trace_id
        self._project_id = project_id
        self._started_at = datetime.now(UTC)
        self._span_id = str(uuid.uuid4())
        self._output: str | None = None

    def set_output(self, value: Any) -> None:
        """Optionally record the agent's final output for the span."""
        try:
            self._output = str(value) if value is not None else None
        except Exception:  # noqa: BLE001
            pass  # fail-open

    def _finish(
        self,
        status: ToolCallStatus = ToolCallStatus.SUCCESS,
        error: str | None = None,
    ) -> None:
        """Emit the agent span.  Always called — never swallowed."""
        try:
            span = ToolCallSpan(
                span_id=self._span_id,
                server_name=self._agent_name or "agent",
                tool_name=f"run/{self._agent_name or 'agent'}",
                started_at=self._started_at,
                ended_at=datetime.now(UTC),
                status=status,
                error=error,
                agent_name=self._agent_name,
                session_id=self._session_id,
                trace_id=self._trace_id,
                span_type="agent",
                project_id=self._project_id or "",
                output_result=self._output,
            )
            self._client.buffer_span(span)
            logger.debug(
                "trace.agent_span",
                agent=self._agent_name,
                status=status,
                latency_ms=span.latency_ms,
            )
        except Exception:  # noqa: BLE001
            pass  # fail-open — tracing must never break agent code

    # ── Async context manager ─────────────────────────────────────────────

    async def __aenter__(self) -> AgentTrace:
        return self

    async def __aexit__(
        self,
        exc_type: type | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> bool:
        if exc_value is not None:
            status = (
                ToolCallStatus.TIMEOUT
                if isinstance(exc_value, (TimeoutError, asyncio.CancelledError))
                else ToolCallStatus.ERROR
            )
            self._finish(status=status, error=f"{type(exc_value).__name__}: {exc_value}")
        else:
            self._finish(status=ToolCallStatus.SUCCESS)
        return False  # NEVER suppress exceptions — always re-raise

    # ── Sync context manager ──────────────────────────────────────────────

    def __enter__(self) -> AgentTrace:
        return self

    def __exit__(
        self,
        exc_type: type | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        if exc_value is not None:
            status = (
                ToolCallStatus.TIMEOUT
                if isinstance(exc_value, (TimeoutError, asyncio.CancelledError))
                else ToolCallStatus.ERROR
            )
            self._finish(status=status, error=f"{type(exc_value).__name__}: {exc_value}")
        else:
            self._finish(status=ToolCallStatus.SUCCESS)


def trace(
    func: F | None = None,
    *,
    client: Any = None,
    agent_name: str | None = None,
    session_id: str | None = None,
    trace_id: str | None = None,
) -> Any:
    """Wrap an agent function or async context manager to capture its full lifecycle.

    Works as a **decorator** (async functions only) and as a **context manager**
    (both sync and async).

    The wrapped function/block captures:
    - Start + end timestamps → latency on the span
    - Any exception raised → ``status=error`` with ``error="ExcType: message"``
    - ``asyncio.CancelledError`` → ``status=timeout``
    - Optional output via ``t.set_output(value)`` in context manager mode

    A global :class:`~langsight.sdk.client.LangSightClient` from
    ``langsight.auto_patch()`` is used if ``client`` is not explicitly provided.

    Args:
        func: The async function to wrap (when used as a bare ``@langsight.trace``).
        client: :class:`~langsight.sdk.client.LangSightClient` to use.  Defaults to
            the global auto-patch client.
        agent_name: Label for this agent span.  Defaults to the function name.
        session_id: Groups spans into one session.  Falls back to the context
            variable set by :func:`~langsight.sdk.auto_patch.session`.
        trace_id: Links multi-agent traces.

    Usage::

        @langsight.trace(agent_name="orchestrator")
        async def run(question: str) -> str:
            ...

        async with langsight.trace(agent_name="analyst") as t:
            result = await analyst.analyze(question)
            t.set_output(result)
    """
    # ── Decorator-factory or context manager: trace(agent_name="x") ────────
    # Returns an object that works BOTH as @trace(agent_name="x") decorator
    # AND as `async with trace(agent_name="x") as t:` context manager.
    if func is None:
        _cm = _make_trace_cm(
            client=client, agent_name=agent_name, session_id=session_id, trace_id=trace_id
        )

        class _TraceProxy:
            """Dual-mode: decorator factory + async/sync context manager.

            The same AgentTrace instance (_cm) is used for both enter and exit
            so the span lifecycle is preserved correctly.
            """

            def __call__(self, fn: F) -> F:
                return _decorate(
                    fn,
                    client=client,
                    agent_name=agent_name or fn.__name__,
                    session_id=session_id,
                    trace_id=trace_id,
                )

            async def __aenter__(self) -> Any:
                return await _cm.__aenter__()

            async def __aexit__(self, *args: Any) -> None:
                await _cm.__aexit__(*args)

            def __enter__(self) -> Any:
                return _cm.__enter__()

            def __exit__(self, *args: Any) -> None:
                _cm.__exit__(*args)

        return _TraceProxy()  # type: ignore[return-value]

    # ── Decorator mode: @langsight.trace  or  @langsight.trace(...) ────────
    if callable(func):
        return _decorate(
            func,
            client=client,
            agent_name=agent_name or func.__name__,
            session_id=session_id,
            trace_id=trace_id,
        )

    raise TypeError(f"trace() expected a callable or None, got {type(func)}")


def _make_trace_cm(
    client: Any = None,
    agent_name: str | None = None,
    session_id: str | None = None,
    trace_id: str | None = None,
) -> AgentTrace:
    """Return an AgentTrace context manager."""
    from langsight.sdk.auto_patch import _agent_ctx, _global_client, _session_ctx, _trace_ctx

    resolved_client = client or _global_client
    if resolved_client is None:
        # Return a no-op trace if no client available
        return _NoopTrace()  # type: ignore[return-value]

    return AgentTrace(
        client=resolved_client,
        agent_name=agent_name or _agent_ctx.get(),
        session_id=session_id or _session_ctx.get(),
        trace_id=trace_id or _trace_ctx.get(),
        project_id=getattr(resolved_client, "_project_id", None),
    )


def _decorate(
    func: F,
    client: Any = None,
    agent_name: str | None = None,
    session_id: str | None = None,
    trace_id: str | None = None,
) -> F:
    """Apply trace wrapping to an async function."""

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        t = _make_trace_cm(
            client=client,
            agent_name=agent_name or func.__name__,
            session_id=session_id,
            trace_id=trace_id,
        )
        async with t:
            result = await func(*args, **kwargs)
            t.set_output(result)
            return result

    return wrapper  # type: ignore[return-value]


class _NoopTrace:
    """No-op trace when no LangSight client is configured — fail-open."""

    def set_output(self, value: Any) -> None:
        pass

    async def __aenter__(self) -> _NoopTrace:
        return self

    async def __aexit__(self, *_: Any) -> bool:
        return False

    def __enter__(self) -> _NoopTrace:
        return self

    def __exit__(self, *_: Any) -> None:
        pass
