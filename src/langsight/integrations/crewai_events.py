# mypy: disable-error-code="untyped-decorator"
"""
CrewAI Event Bus integration for LangSight.

Subscribes to CrewAI's native event bus (``crewai.events``) to capture
crew / task / agent / tool / LLM lifecycle spans with full attribution —
agent_role, task_name, and task_id come pre-populated on every event.

This replaces the fragile monkey-patching of ``BaseTool.run`` with the
forward-compatible event bus API that CrewAI itself uses for its own
telemetry (``TraceCollectionListener``).

Activated automatically by ``auto_patch()`` when CrewAI >= 1.5 is detected.
Falls back to monkey-patching on older versions.

Usage (zero-code):
    import langsight
    langsight.auto_patch()   # detects CrewAI event bus automatically

    crew = Crew(agents=[...], tasks=[...])
    result = crew.kickoff()  # all spans captured via event bus
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

import structlog

from langsight.sdk.models import ToolCallSpan, ToolCallStatus

logger = structlog.get_logger()

# MCP tool name pattern: mcp__<server>__<tool>
_MCP_PREFIX = "mcp__"


def _parse_mcp_tool_name(raw_name: str) -> tuple[str, str]:
    """Parse a tool name into (server_name, tool_name).

    MCP tools: ``mcp__server__tool`` → ``("server", "tool")``
    Regular tools: ``scrape_website`` → ``("crewai", "scrape_website")``
    """
    if "__" in raw_name:
        parts = raw_name.split("__", 2)
        server = parts[1] if len(parts) >= 2 else "crewai"
        tool = parts[2] if len(parts) == 3 else raw_name
        return server, tool
    return "crewai", raw_name


class LangSightCrewAIEventListener:
    """CrewAI event bus listener that converts events to LangSight spans.

    NOT a subclass of ``BaseEventListener`` — we register handlers directly
    on the singleton event bus to avoid the ABC constraint and keep the
    dependency lazy (crewai is only imported inside ``setup()``).

    Parameters:
        client_resolver:
            A callable that returns the current ``LangSightClient`` or None.
            Typically ``auto_patch._resolve_client``.
    """

    def __init__(self, client_resolver: Callable[[], Any | None]) -> None:
        self._resolve_client = client_resolver
        self._session_id: str | None = None
        self._listeners_setup = False

        # Track in-flight spans for start/end pairing
        self._crew_started_at: datetime | None = None
        self._crew_name: str | None = None
        self._task_starts: dict[str, datetime] = {}  # task_id → started_at
        self._agent_starts: dict[str, datetime] = {}  # agent_id → started_at
        self._tool_starts: dict[str, datetime] = {}  # tool_name:agent_id → started_at
        self._a2a_delegation_starts: dict[str, datetime] = {}  # agent_id → started_at
        self._a2a_conversation_starts: dict[str, datetime] = {}  # agent_id → started_at

    def setup(self) -> bool:
        """Register all event handlers on the CrewAI event bus.

        Returns True if successful, False if crewai.events is not available.
        """
        if self._listeners_setup:
            return True

        try:
            from crewai.events.event_bus import crewai_event_bus
            from crewai.events.types.agent_events import (
                AgentExecutionCompletedEvent,
                AgentExecutionErrorEvent,
                AgentExecutionStartedEvent,
            )
            from crewai.events.types.crew_events import (
                CrewKickoffCompletedEvent,
                CrewKickoffFailedEvent,
                CrewKickoffStartedEvent,
            )
            from crewai.events.types.llm_events import (
                LLMCallCompletedEvent,
                LLMCallFailedEvent,
                LLMCallStartedEvent,
            )
            from crewai.events.types.task_events import (
                TaskCompletedEvent,
                TaskFailedEvent,
                TaskStartedEvent,
            )
            from crewai.events.types.tool_usage_events import (
                ToolUsageErrorEvent,
                ToolUsageFinishedEvent,
                ToolUsageStartedEvent,
            )
        except ImportError:
            logger.debug("crewai_events.import_failed", reason="crewai.events not available")
            return False

        # A2A delegation events — optional (not present in all CrewAI versions)
        _a2a_available = False
        try:
            from crewai.events.types.a2a_events import (
                A2AConversationCompletedEvent,
                A2AConversationStartedEvent,
                A2ADelegationCompletedEvent,
                A2ADelegationStartedEvent,
            )

            _a2a_available = True
        except ImportError:
            pass  # A2A events not available in this CrewAI version

        bus = crewai_event_bus

        # ── Crew lifecycle ─────────────────────────────────────────────
        @bus.on(CrewKickoffStartedEvent)
        def _on_crew_started(source: Any, event: CrewKickoffStartedEvent) -> None:
            self._handle_crew_started(event)

        @bus.on(CrewKickoffCompletedEvent)
        def _on_crew_completed(source: Any, event: CrewKickoffCompletedEvent) -> None:
            self._handle_crew_completed(event)

        @bus.on(CrewKickoffFailedEvent)
        def _on_crew_failed(source: Any, event: CrewKickoffFailedEvent) -> None:
            self._handle_crew_failed(event)

        # ── Task lifecycle ─────────────────────────────────────────────
        @bus.on(TaskStartedEvent)
        def _on_task_started(source: Any, event: TaskStartedEvent) -> None:
            self._handle_task_started(event)

        @bus.on(TaskCompletedEvent)
        def _on_task_completed(source: Any, event: TaskCompletedEvent) -> None:
            self._handle_task_completed(event)

        @bus.on(TaskFailedEvent)
        def _on_task_failed(source: Any, event: TaskFailedEvent) -> None:
            self._handle_task_failed(event)

        # ── Agent execution ────────────────────────────────────────────
        @bus.on(AgentExecutionStartedEvent)
        def _on_agent_started(source: Any, event: AgentExecutionStartedEvent) -> None:
            self._handle_agent_started(event)

        @bus.on(AgentExecutionCompletedEvent)
        def _on_agent_completed(source: Any, event: AgentExecutionCompletedEvent) -> None:
            self._handle_agent_completed(event)

        @bus.on(AgentExecutionErrorEvent)
        def _on_agent_error(source: Any, event: AgentExecutionErrorEvent) -> None:
            self._handle_agent_error(event)

        # ── Tool usage ─────────────────────────────────────────────────
        @bus.on(ToolUsageStartedEvent)
        def _on_tool_started(source: Any, event: ToolUsageStartedEvent) -> None:
            self._handle_tool_started(event)

        @bus.on(ToolUsageFinishedEvent)
        def _on_tool_finished(source: Any, event: ToolUsageFinishedEvent) -> None:
            self._handle_tool_finished(event)

        @bus.on(ToolUsageErrorEvent)
        def _on_tool_error(source: Any, event: ToolUsageErrorEvent) -> None:
            self._handle_tool_error(event)

        # ── LLM calls ─────────────────────────────────────────────────
        @bus.on(LLMCallStartedEvent)
        def _on_llm_started(source: Any, event: LLMCallStartedEvent) -> None:
            self._handle_llm_started(event)

        @bus.on(LLMCallCompletedEvent)
        def _on_llm_completed(source: Any, event: LLMCallCompletedEvent) -> None:
            self._handle_llm_completed(event)

        @bus.on(LLMCallFailedEvent)
        def _on_llm_failed(source: Any, event: LLMCallFailedEvent) -> None:
            self._handle_llm_failed(event)

        # ── A2A delegation (agent handoff) ─────────────────────────────
        _n_handlers = 15
        if _a2a_available:

            @bus.on(A2ADelegationStartedEvent)
            def _on_a2a_delegation_started(source: Any, event: A2ADelegationStartedEvent) -> None:
                self._handle_a2a_delegation_started(event)

            @bus.on(A2ADelegationCompletedEvent)
            def _on_a2a_delegation_completed(
                source: Any, event: A2ADelegationCompletedEvent
            ) -> None:
                self._handle_a2a_delegation_completed(event)

            @bus.on(A2AConversationStartedEvent)
            def _on_a2a_conversation_started(
                source: Any, event: A2AConversationStartedEvent
            ) -> None:
                self._handle_a2a_conversation_started(event)

            @bus.on(A2AConversationCompletedEvent)
            def _on_a2a_conversation_completed(
                source: Any, event: A2AConversationCompletedEvent
            ) -> None:
                self._handle_a2a_conversation_completed(event)

            _n_handlers = 19

        self._listeners_setup = True
        logger.info(
            "crewai_events.setup_complete", events_registered=_n_handlers, a2a=_a2a_available
        )
        return True

    # ── Helpers ─────────────────────────────────────────────────────────

    def _get_session_id(self) -> str | None:
        """Return the current session_id, falling back to auto_patch context."""
        if self._session_id:
            return self._session_id
        try:
            from langsight.sdk.auto_patch import _session_ctx

            return _session_ctx.get()
        except ImportError:
            return None

    def _get_project_id(self, client: Any) -> str | None:
        """Extract project_id from client."""
        return getattr(client, "_project_id", None) or None

    def _buffer_span(self, span: ToolCallSpan) -> None:
        """Send a span to the LangSight client buffer."""
        client = self._resolve_client()
        if client is None:
            return
        client.buffer_span(span)
        logger.debug(
            "crewai_events.span_buffered",
            span_type=span.span_type,
            tool=span.tool_name,
            agent=span.agent_name,
            latency_ms=span.latency_ms,
        )

    @staticmethod
    def _ensure_utc(dt: datetime) -> datetime:
        """Ensure a datetime is UTC-aware. CrewAI emits naive datetimes."""
        from datetime import UTC

        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt

    def _make_span(
        self,
        *,
        server_name: str,
        tool_name: str,
        started_at: datetime,
        status: ToolCallStatus,
        span_type: str = "tool_call",
        agent_name: str | None = None,
        error: str | None = None,
        output_result: str | None = None,
        input_args: dict[str, Any] | None = None,
        llm_input: str | None = None,
        llm_output: str | None = None,
        model_id: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        ended_at: datetime | None = None,
    ) -> ToolCallSpan:
        """Build a ToolCallSpan with common fields populated.

        When ``ended_at`` is provided (e.g. from ToolUsageFinishedEvent.finished_at),
        it is used directly instead of ``datetime.now(UTC)`` — this gives accurate
        latency even when the event handler runs after the fact.
        """
        from datetime import UTC

        started_at = self._ensure_utc(started_at)
        if ended_at is not None:
            ended_at = self._ensure_utc(ended_at)
        else:
            ended_at = datetime.now(UTC)

        latency_ms = round((ended_at - started_at).total_seconds() * 1000, 2)

        client = self._resolve_client()
        project_id = self._get_project_id(client) if client else None

        return ToolCallSpan(
            server_name=server_name,
            tool_name=tool_name,
            started_at=started_at,
            ended_at=ended_at,
            latency_ms=latency_ms,
            status=status,
            span_type=span_type,  # type: ignore[arg-type]
            agent_name=agent_name,
            session_id=self._get_session_id(),
            error=error,
            output_result=output_result[:2000] if output_result else None,
            input_args=input_args,
            llm_input=llm_input[:4000] if llm_input else None,
            llm_output=llm_output[:4000] if llm_output else None,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            project_id=project_id,
            lineage_provenance="explicit",
            schema_version="1.0",
        )

    # ── Crew handlers ──────────────────────────────────────────────────

    def _handle_crew_started(self, event: Any) -> None:
        self._crew_started_at = event.timestamp
        self._crew_name = getattr(event, "crew_name", None) or "crew"

        # Auto-generate session_id if none is active
        session = self._get_session_id()
        if not session:
            self._session_id = uuid.uuid4().hex
            try:
                from langsight.sdk.auto_patch import _session_ctx

                _session_ctx.set(self._session_id)
            except ImportError:
                pass

        logger.info(
            "crewai_events.crew_started",
            crew=self._crew_name,
            session_id=self._get_session_id(),
        )

    def _handle_crew_completed(self, event: Any) -> None:
        started = self._crew_started_at or event.timestamp
        crew_name = self._crew_name or "crew"
        total_tokens = getattr(event, "total_tokens", 0)

        output_str = None
        output = getattr(event, "output", None)
        if output is not None:
            output_str = str(output)

        span = self._make_span(
            server_name="crewai",
            tool_name=f"crew:{crew_name}",
            started_at=started,
            status=ToolCallStatus.SUCCESS,
            span_type="agent",
            agent_name=crew_name,
            output_result=output_str,
            input_tokens=total_tokens if total_tokens else None,
        )
        self._buffer_span(span)

        # Flush all buffered spans
        client = self._resolve_client()
        if client is not None:
            self._flush_client(client)

        self._crew_started_at = None
        self._crew_name = None

    def _handle_crew_failed(self, event: Any) -> None:
        started = self._crew_started_at or event.timestamp
        crew_name = self._crew_name or "crew"
        error_msg = getattr(event, "error", None) or "crew kickoff failed"

        span = self._make_span(
            server_name="crewai",
            tool_name=f"crew:{crew_name}",
            started_at=started,
            status=ToolCallStatus.ERROR,
            span_type="agent",
            agent_name=crew_name,
            error=str(error_msg),
        )
        self._buffer_span(span)

        client = self._resolve_client()
        if client is not None:
            self._flush_client(client)

        self._crew_started_at = None
        self._crew_name = None

    # ── Task handlers ──────────────────────────────────────────────────

    def _handle_task_started(self, event: Any) -> None:
        task = getattr(event, "task", None)
        task_id = str(getattr(task, "id", "")) if task else ""
        if task_id:
            self._task_starts[task_id] = event.timestamp

    def _handle_task_completed(self, event: Any) -> None:
        task = getattr(event, "task", None)
        task_id = str(getattr(task, "id", "")) if task else ""
        started = self._task_starts.pop(task_id, event.timestamp)

        task_name = _extract_task_name(task)
        agent_role = _extract_agent_role_from_task(task)

        output = getattr(event, "output", None)
        output_str = str(output) if output is not None else None

        span = self._make_span(
            server_name="crewai",
            tool_name=f"task:{task_name}",
            started_at=started,
            status=ToolCallStatus.SUCCESS,
            span_type="agent",
            agent_name=agent_role,
            output_result=output_str,
        )
        self._buffer_span(span)

    def _handle_task_failed(self, event: Any) -> None:
        task = getattr(event, "task", None)
        task_id = str(getattr(task, "id", "")) if task else ""
        started = self._task_starts.pop(task_id, event.timestamp)

        task_name = _extract_task_name(task)
        agent_role = _extract_agent_role_from_task(task)
        error_msg = getattr(event, "error", None) or "task failed"

        span = self._make_span(
            server_name="crewai",
            tool_name=f"task:{task_name}",
            started_at=started,
            status=ToolCallStatus.ERROR,
            span_type="agent",
            agent_name=agent_role,
            error=str(error_msg),
        )
        self._buffer_span(span)

    # ── Agent execution handlers ───────────────────────────────────────

    def _handle_agent_started(self, event: Any) -> None:
        agent = getattr(event, "agent", None)
        agent_id = str(getattr(agent, "id", "")) if agent else ""
        if agent_id:
            self._agent_starts[agent_id] = event.timestamp

    def _handle_agent_completed(self, event: Any) -> None:
        agent = getattr(event, "agent", None)
        agent_id = str(getattr(agent, "id", "")) if agent else ""
        started = self._agent_starts.pop(agent_id, event.timestamp)

        agent_role = getattr(agent, "role", None) or "agent"
        output = getattr(event, "output", None)

        span = self._make_span(
            server_name="crewai",
            tool_name=f"agent:{agent_role}",
            started_at=started,
            status=ToolCallStatus.SUCCESS,
            span_type="agent",
            agent_name=agent_role,
            output_result=str(output) if output else None,
        )
        self._buffer_span(span)

    def _handle_agent_error(self, event: Any) -> None:
        agent = getattr(event, "agent", None)
        agent_id = str(getattr(agent, "id", "")) if agent else ""
        started = self._agent_starts.pop(agent_id, event.timestamp)

        agent_role = getattr(agent, "role", None) or "agent"
        error_msg = getattr(event, "error", None) or "agent execution failed"

        span = self._make_span(
            server_name="crewai",
            tool_name=f"agent:{agent_role}",
            started_at=started,
            status=ToolCallStatus.ERROR,
            span_type="agent",
            agent_name=agent_role,
            error=str(error_msg),
        )
        self._buffer_span(span)

    # ── Tool usage handlers ────────────────────────────────────────────

    def _handle_tool_started(self, event: Any) -> None:
        tool_name = getattr(event, "tool_name", "unknown")
        agent_id = getattr(event, "agent_id", "") or ""
        key = f"{tool_name}:{agent_id}"
        self._tool_starts[key] = event.timestamp

    def _handle_tool_finished(self, event: Any) -> None:
        raw_name = getattr(event, "tool_name", "unknown")
        agent_id = getattr(event, "agent_id", "") or ""
        key = f"{raw_name}:{agent_id}"

        # Prefer event's own timing if available
        started = getattr(event, "started_at", None) or self._tool_starts.pop(key, event.timestamp)
        if key in self._tool_starts:
            self._tool_starts.pop(key, None)

        server_name, tool_name = _parse_mcp_tool_name(raw_name)
        agent_role = getattr(event, "agent_role", None)
        output = getattr(event, "output", None)
        tool_args = getattr(event, "tool_args", None)
        from_cache = getattr(event, "from_cache", False)

        input_args = None
        if tool_args is not None:
            if isinstance(tool_args, dict):
                input_args = tool_args
            elif isinstance(tool_args, str):
                input_args = {"input": tool_args}

        output_str = str(output) if output is not None else None
        if from_cache and output_str:
            output_str = f"[cached] {output_str}"

        finished = getattr(event, "finished_at", None)

        span = self._make_span(
            server_name=server_name,
            tool_name=tool_name,
            started_at=started,
            status=ToolCallStatus.SUCCESS,
            span_type="tool_call",
            agent_name=agent_role,
            output_result=output_str,
            input_args=input_args,
            ended_at=finished,
        )
        self._buffer_span(span)

    def _handle_tool_error(self, event: Any) -> None:
        raw_name = getattr(event, "tool_name", "unknown")
        agent_id = getattr(event, "agent_id", "") or ""
        key = f"{raw_name}:{agent_id}"
        started = self._tool_starts.pop(key, event.timestamp)

        server_name, tool_name = _parse_mcp_tool_name(raw_name)
        agent_role = getattr(event, "agent_role", None)
        error_msg = getattr(event, "error", None) or "tool execution failed"
        tool_args = getattr(event, "tool_args", None)

        input_args = None
        if tool_args is not None:
            if isinstance(tool_args, dict):
                input_args = tool_args
            elif isinstance(tool_args, str):
                input_args = {"input": tool_args}

        span = self._make_span(
            server_name=server_name,
            tool_name=tool_name,
            started_at=started,
            status=ToolCallStatus.ERROR,
            span_type="tool_call",
            agent_name=agent_role,
            error=str(error_msg),
            input_args=input_args,
        )
        self._buffer_span(span)

    # ── LLM call handlers ──────────────────────────────────────────────

    def _handle_llm_started(self, event: Any) -> None:
        # LLM calls don't have a unique ID, so we track by agent_id + timestamp
        # The completed event carries its own timing, so we just log here
        pass  # No state to track — LLM completed events are self-contained

    def _handle_llm_completed(self, event: Any) -> None:
        model = getattr(event, "model", None)
        agent_role = getattr(event, "agent_role", None)
        response = getattr(event, "response", None)
        messages = getattr(event, "messages", None)

        # Build llm_input from messages
        llm_input = None
        if messages is not None:
            if isinstance(messages, str):
                llm_input = messages
            elif isinstance(messages, list):
                # Extract last user message for brevity
                user_msgs = [m for m in messages if isinstance(m, dict) and m.get("role") == "user"]
                if user_msgs:
                    last = user_msgs[-1]
                    content = last.get("content", "")
                    llm_input = str(content) if content else None

        llm_output = str(response) if response is not None else None

        span = self._make_span(
            server_name="crewai",
            tool_name=f"llm:{model or 'unknown'}",
            started_at=event.timestamp,
            status=ToolCallStatus.SUCCESS,
            span_type="agent",
            agent_name=agent_role,
            llm_input=llm_input,
            llm_output=llm_output,
            model_id=model,
        )
        self._buffer_span(span)

    def _handle_llm_failed(self, event: Any) -> None:
        model = getattr(event, "model", None)
        agent_role = getattr(event, "agent_role", None)
        error_msg = getattr(event, "error", None) or "LLM call failed"

        span = self._make_span(
            server_name="crewai",
            tool_name=f"llm:{model or 'unknown'}",
            started_at=event.timestamp,
            status=ToolCallStatus.ERROR,
            span_type="agent",
            agent_name=agent_role,
            error=str(error_msg),
            model_id=model,
        )
        self._buffer_span(span)

    # ── A2A delegation (agent handoff) handlers ──────────────────────

    def _handle_a2a_delegation_started(self, event: Any) -> None:
        agent_id = getattr(event, "agent_id", "") or ""
        self._a2a_delegation_starts[agent_id] = event.timestamp

    def _handle_a2a_delegation_completed(self, event: Any) -> None:
        agent_id = getattr(event, "agent_id", "") or ""
        started = self._a2a_delegation_starts.pop(agent_id, event.timestamp)

        from_agent = getattr(event, "agent_role", None) or "agent"
        # The target is the A2A agent being delegated to
        endpoint = getattr(event, "endpoint", None) or ""
        a2a_agent_name = getattr(event, "a2a_agent_name", None)
        target_name = a2a_agent_name or endpoint or agent_id
        status_str = getattr(event, "status", "completed")
        result = getattr(event, "result", None)
        error = getattr(event, "error", None)

        is_success = status_str == "completed"

        started = self._ensure_utc(started)

        client = self._resolve_client()
        project_id = self._get_project_id(client) if client else None

        span = ToolCallSpan.record(
            server_name=from_agent,
            tool_name=f"→ {target_name}",
            started_at=started,
            status=ToolCallStatus.SUCCESS if is_success else ToolCallStatus.ERROR,
            span_type="handoff",
            agent_name=from_agent,
            target_agent_name=target_name,
            session_id=self._get_session_id(),
            error=str(error) if error and not is_success else None,
            output_result=str(result)[:2000] if result else None,
            project_id=project_id,
            lineage_provenance="explicit",
            schema_version="1.0",
        )
        self._buffer_span(span)

    def _handle_a2a_conversation_started(self, event: Any) -> None:
        agent_id = getattr(event, "agent_id", "") or ""
        self._a2a_conversation_starts[agent_id] = event.timestamp

    def _handle_a2a_conversation_completed(self, event: Any) -> None:
        agent_id = getattr(event, "agent_id", "") or ""
        started = self._a2a_conversation_starts.pop(agent_id, event.timestamp)

        a2a_agent_name = getattr(event, "a2a_agent_name", None) or agent_id
        status_str = getattr(event, "status", "completed")
        final_result = getattr(event, "final_result", None)
        error = getattr(event, "error", None)
        total_turns = getattr(event, "total_turns", 0)
        from_agent = getattr(event, "agent_role", None) or "agent"

        is_success = status_str == "completed"

        span = self._make_span(
            server_name="crewai",
            tool_name=f"a2a:{a2a_agent_name}",
            started_at=started,
            status=ToolCallStatus.SUCCESS if is_success else ToolCallStatus.ERROR,
            span_type="agent",
            agent_name=from_agent,
            error=str(error) if error and not is_success else None,
            output_result=(
                f"[{total_turns} turns] {final_result}"[:2000]
                if final_result
                else f"[{total_turns} turns]"
            ),
        )
        self._buffer_span(span)

    # ── Flush helper ───────────────────────────────────────────────────

    @staticmethod
    def _flush_client(client: Any) -> None:
        """Flush the client, handling both sync and async contexts."""
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(client.flush())
            else:
                loop.run_until_complete(client.flush())
        except Exception as exc:  # noqa: BLE001
            logger.warning("crewai_events.flush_error", error=str(exc))


# ── Module-level helpers ───────────────────────────────────────────────


def _extract_task_name(task: Any) -> str:
    """Extract a human-readable task name."""
    if task is None:
        return "unknown_task"
    name = getattr(task, "name", None)
    if name:
        return str(name)
    desc = getattr(task, "description", None)
    if desc:
        return str(desc)[:80]
    return "unknown_task"


def _extract_agent_role_from_task(task: Any) -> str | None:
    """Extract the agent role from a task object."""
    if task is None:
        return None
    agent = getattr(task, "agent", None)
    if agent is None:
        return None
    return getattr(agent, "role", None)
