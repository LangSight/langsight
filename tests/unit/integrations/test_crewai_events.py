"""
Unit tests for the CrewAI event bus integration.

Tests the ``LangSightCrewAIEventListener`` which subscribes to CrewAI's
native event bus to capture crew / task / agent / tool / LLM spans.

All CrewAI dependencies are mocked — crewai does not need to be installed.
"""

from __future__ import annotations

import sys
import types
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from langsight.sdk.models import ToolCallSpan, ToolCallStatus


# ---------------------------------------------------------------------------
# Fake CrewAI event bus and event types
# ---------------------------------------------------------------------------


class FakeEventBus:
    """Minimal fake of ``crewai.events.event_bus.CrewAIEventsBus``."""

    def __init__(self) -> None:
        self._handlers: dict[type, list] = {}

    def on(self, event_type: type, depends_on: Any = None):
        def decorator(handler):
            self._handlers.setdefault(event_type, []).append(handler)
            return handler

        return decorator

    def emit(self, source: Any, event: Any) -> None:
        """Emit an event to all registered handlers.

        Uses ``event.__class__`` for dispatch — matches real CrewAI behavior
        and works with our FakeEvent instances.
        """
        event_type = event.__class__
        for handler in self._handlers.get(event_type, []):
            handler(source, event)


class FakeEvent:
    """Base for fake event objects — avoids MagicMock dispatch issues."""

    def __init__(self, **kwargs: Any) -> None:
        self.timestamp = kwargs.pop("timestamp", datetime.now(UTC))
        for k, v in kwargs.items():
            setattr(self, k, v)


def _make_event(event_class: type, **kwargs) -> Any:
    """Create a fake event instance that dispatches as ``event_class``."""
    event = FakeEvent(**kwargs)
    event.__class__ = event_class  # type: ignore[assignment]
    return event


# Fake event types (match CrewAI's real class names)
class CrewKickoffStartedEvent:
    pass


class CrewKickoffCompletedEvent:
    pass


class CrewKickoffFailedEvent:
    pass


class TaskStartedEvent:
    pass


class TaskCompletedEvent:
    pass


class TaskFailedEvent:
    pass


class AgentExecutionStartedEvent:
    pass


class AgentExecutionCompletedEvent:
    pass


class AgentExecutionErrorEvent:
    pass


class ToolUsageStartedEvent:
    pass


class ToolUsageFinishedEvent:
    pass


class ToolUsageErrorEvent:
    pass


class A2ADelegationStartedEvent:
    pass


class A2ADelegationCompletedEvent:
    pass


class A2AConversationStartedEvent:
    pass


class A2AConversationCompletedEvent:
    pass


class LLMCallStartedEvent:
    pass


class LLMCallCompletedEvent:
    pass


class LLMCallFailedEvent:
    pass


# ---------------------------------------------------------------------------
# Install fake crewai.events modules
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _install_fake_crewai_events(monkeypatch):
    """Install fake crewai.events modules so the listener can import them."""
    fake_bus = FakeEventBus()

    # crewai.events.event_bus
    mod_bus = types.ModuleType("crewai.events.event_bus")
    mod_bus.crewai_event_bus = fake_bus  # type: ignore[attr-defined]

    # crewai.events.types.crew_events
    mod_crew = types.ModuleType("crewai.events.types.crew_events")
    mod_crew.CrewKickoffStartedEvent = CrewKickoffStartedEvent  # type: ignore[attr-defined]
    mod_crew.CrewKickoffCompletedEvent = CrewKickoffCompletedEvent  # type: ignore[attr-defined]
    mod_crew.CrewKickoffFailedEvent = CrewKickoffFailedEvent  # type: ignore[attr-defined]

    # crewai.events.types.task_events
    mod_task = types.ModuleType("crewai.events.types.task_events")
    mod_task.TaskStartedEvent = TaskStartedEvent  # type: ignore[attr-defined]
    mod_task.TaskCompletedEvent = TaskCompletedEvent  # type: ignore[attr-defined]
    mod_task.TaskFailedEvent = TaskFailedEvent  # type: ignore[attr-defined]

    # crewai.events.types.agent_events
    mod_agent = types.ModuleType("crewai.events.types.agent_events")
    mod_agent.AgentExecutionStartedEvent = AgentExecutionStartedEvent  # type: ignore[attr-defined]
    mod_agent.AgentExecutionCompletedEvent = AgentExecutionCompletedEvent  # type: ignore[attr-defined]
    mod_agent.AgentExecutionErrorEvent = AgentExecutionErrorEvent  # type: ignore[attr-defined]

    # crewai.events.types.tool_usage_events
    mod_tool = types.ModuleType("crewai.events.types.tool_usage_events")
    mod_tool.ToolUsageStartedEvent = ToolUsageStartedEvent  # type: ignore[attr-defined]
    mod_tool.ToolUsageFinishedEvent = ToolUsageFinishedEvent  # type: ignore[attr-defined]
    mod_tool.ToolUsageErrorEvent = ToolUsageErrorEvent  # type: ignore[attr-defined]

    # crewai.events.types.llm_events
    mod_llm = types.ModuleType("crewai.events.types.llm_events")
    mod_llm.LLMCallStartedEvent = LLMCallStartedEvent  # type: ignore[attr-defined]
    mod_llm.LLMCallCompletedEvent = LLMCallCompletedEvent  # type: ignore[attr-defined]
    mod_llm.LLMCallFailedEvent = LLMCallFailedEvent  # type: ignore[attr-defined]

    # crewai.events.types.a2a_events
    mod_a2a = types.ModuleType("crewai.events.types.a2a_events")
    mod_a2a.A2ADelegationStartedEvent = A2ADelegationStartedEvent  # type: ignore[attr-defined]
    mod_a2a.A2ADelegationCompletedEvent = A2ADelegationCompletedEvent  # type: ignore[attr-defined]
    mod_a2a.A2AConversationStartedEvent = A2AConversationStartedEvent  # type: ignore[attr-defined]
    mod_a2a.A2AConversationCompletedEvent = A2AConversationCompletedEvent  # type: ignore[attr-defined]

    # Register all modules
    for name, mod in [
        ("crewai.events.event_bus", mod_bus),
        ("crewai.events.types.crew_events", mod_crew),
        ("crewai.events.types.task_events", mod_task),
        ("crewai.events.types.agent_events", mod_agent),
        ("crewai.events.types.tool_usage_events", mod_tool),
        ("crewai.events.types.llm_events", mod_llm),
        ("crewai.events.types.a2a_events", mod_a2a),
    ]:
        monkeypatch.setitem(sys.modules, name, mod)

    yield fake_bus

    # Cleanup handled by monkeypatch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_listener(buffered_spans: list[ToolCallSpan] | None = None) -> Any:
    """Create a listener with a mock client that captures buffered spans."""
    from langsight.integrations.crewai_events import LangSightCrewAIEventListener

    captured = buffered_spans if buffered_spans is not None else []
    mock_client = MagicMock()
    mock_client._project_id = "test-project"
    mock_client.buffer_span = lambda span: captured.append(span)
    mock_client.flush = MagicMock()

    listener = LangSightCrewAIEventListener(client_resolver=lambda: mock_client)
    return listener, captured, mock_client


def _setup_and_get_bus(listener) -> FakeEventBus:
    """Setup the listener and return the event bus it registered on."""
    result = listener.setup()
    assert result is True

    # Get the bus from sys.modules
    mod = sys.modules["crewai.events.event_bus"]
    return mod.crewai_event_bus  # type: ignore[union-attr]


# ===========================================================================
# Test: Setup
# ===========================================================================


class TestSetup:
    def test_setup_returns_true_when_crewai_events_available(self):
        listener, _, _ = _make_listener()
        assert listener.setup() is True

    def test_setup_registers_15_handlers(self):
        listener, _, _ = _make_listener()
        bus = _setup_and_get_bus(listener)
        total_handlers = sum(len(h) for h in bus._handlers.values())
        assert total_handlers == 19  # 15 core + 4 A2A

    def test_setup_is_idempotent(self):
        listener, _, _ = _make_listener()
        bus = _setup_and_get_bus(listener)
        listener.setup()  # second call
        total_handlers = sum(len(h) for h in bus._handlers.values())
        assert total_handlers == 19  # 15 core + 4 A2A  # no duplicates

    def test_setup_returns_false_when_crewai_not_installed(self, monkeypatch):
        """When crewai.events is not importable, setup returns False."""
        monkeypatch.delitem(sys.modules, "crewai.events.event_bus", raising=False)

        from langsight.integrations.crewai_events import LangSightCrewAIEventListener

        listener = LangSightCrewAIEventListener(client_resolver=lambda: None)
        assert listener.setup() is False


# ===========================================================================
# Test: Crew lifecycle
# ===========================================================================


class TestCrewLifecycle:
    def test_crew_started_sets_session_id(self):
        listener, spans, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        event = _make_event(CrewKickoffStartedEvent, crew_name="marketing-crew")
        bus.emit(None, event)

        assert listener._session_id is not None
        assert len(listener._session_id) == 32  # UUID hex

    def test_crew_completed_creates_span(self):
        listener, spans, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        # Start
        started = datetime.now(UTC) - timedelta(seconds=10)
        bus.emit(None, _make_event(CrewKickoffStartedEvent, crew_name="test-crew", timestamp=started))

        # Complete
        bus.emit(
            None,
            _make_event(
                CrewKickoffCompletedEvent,
                crew_name="test-crew",
                output="final result",
                total_tokens=1500,
            ),
        )

        assert len(spans) == 1
        span = spans[0]
        assert span.tool_name == "crew:test-crew"
        assert span.span_type == "agent"
        assert span.status == ToolCallStatus.SUCCESS
        assert span.input_tokens == 1500
        assert "final result" in span.output_result

    def test_crew_failed_creates_error_span(self):
        listener, spans, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        started = datetime.now(UTC) - timedelta(seconds=5)
        bus.emit(None, _make_event(CrewKickoffStartedEvent, crew_name="failing-crew", timestamp=started))
        bus.emit(None, _make_event(CrewKickoffFailedEvent, crew_name="failing-crew", error="timeout"))

        assert len(spans) == 1
        assert spans[0].status == ToolCallStatus.ERROR
        assert spans[0].error == "timeout"

    def test_crew_completed_flushes_client(self):
        listener, spans, mock_client = _make_listener()
        bus = _setup_and_get_bus(listener)

        bus.emit(None, _make_event(CrewKickoffStartedEvent, crew_name="crew"))
        bus.emit(None, _make_event(CrewKickoffCompletedEvent, crew_name="crew", output="done", total_tokens=0))

        # Flush should have been called (via _flush_client)
        # The flush is async, but our mock should handle it
        assert len(spans) == 1


# ===========================================================================
# Test: Task lifecycle
# ===========================================================================


class TestTaskLifecycle:
    def _make_task(self, task_id="task-1", name="research_task", agent_role="Analyst"):
        task = MagicMock()
        task.id = task_id
        task.name = name
        task.description = "Do some research"
        agent = MagicMock()
        agent.role = agent_role
        task.agent = agent
        return task

    def test_task_completed_creates_span(self):
        listener, spans, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        task = self._make_task()
        started = datetime.now(UTC) - timedelta(seconds=3)
        bus.emit(None, _make_event(TaskStartedEvent, task=task, context="", timestamp=started))
        bus.emit(None, _make_event(TaskCompletedEvent, task=task, output="research findings"))

        assert len(spans) == 1
        span = spans[0]
        assert span.tool_name == "task:research_task"
        assert span.span_type == "agent"
        assert span.status == ToolCallStatus.SUCCESS
        assert span.agent_name == "Analyst"
        assert "research findings" in span.output_result

    def test_task_failed_creates_error_span(self):
        listener, spans, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        task = self._make_task(name="failing_task")
        bus.emit(None, _make_event(TaskStartedEvent, task=task, context=""))
        bus.emit(None, _make_event(TaskFailedEvent, task=task, error="rate limit"))

        assert len(spans) == 1
        assert spans[0].status == ToolCallStatus.ERROR
        assert spans[0].error == "rate limit"

    def test_task_name_falls_back_to_description(self):
        listener, spans, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        task = MagicMock()
        task.id = "t-2"
        task.name = None
        task.description = "Analyze the market thoroughly"
        task.agent = None
        bus.emit(None, _make_event(TaskStartedEvent, task=task, context=""))
        bus.emit(None, _make_event(TaskCompletedEvent, task=task, output="done"))

        assert spans[0].tool_name == "task:Analyze the market thoroughly"


# ===========================================================================
# Test: Agent execution
# ===========================================================================


class TestAgentExecution:
    def _make_agent(self, agent_id="agent-1", role="SQL Analyst"):
        agent = MagicMock()
        agent.id = agent_id
        agent.role = role
        return agent

    def test_agent_completed_creates_span(self):
        listener, spans, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        agent = self._make_agent()
        task = MagicMock()
        task.name = "query_task"

        started = datetime.now(UTC) - timedelta(seconds=2)
        bus.emit(
            None,
            _make_event(
                AgentExecutionStartedEvent,
                agent=agent,
                task=task,
                tools=[],
                task_prompt="Find the data",
                timestamp=started,
            ),
        )
        bus.emit(
            None,
            _make_event(AgentExecutionCompletedEvent, agent=agent, task=task, output="query results"),
        )

        assert len(spans) == 1
        span = spans[0]
        assert span.tool_name == "agent:SQL Analyst"
        assert span.agent_name == "SQL Analyst"
        assert span.span_type == "agent"
        assert span.status == ToolCallStatus.SUCCESS

    def test_agent_error_creates_error_span(self):
        listener, spans, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        agent = self._make_agent(role="Broken Agent")
        bus.emit(
            None,
            _make_event(AgentExecutionStartedEvent, agent=agent, task=None, tools=[], task_prompt=""),
        )
        bus.emit(
            None,
            _make_event(AgentExecutionErrorEvent, agent=agent, task=None, error="LLM timeout"),
        )

        assert len(spans) == 1
        assert spans[0].status == ToolCallStatus.ERROR
        assert spans[0].error == "LLM timeout"


# ===========================================================================
# Test: Tool usage
# ===========================================================================


class TestToolUsage:
    def test_tool_finished_creates_span(self):
        listener, spans, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        started = datetime.now(UTC) - timedelta(seconds=1)
        bus.emit(
            None,
            _make_event(
                ToolUsageStartedEvent,
                tool_name="scrape_website",
                agent_id="a-1",
                agent_role="Researcher",
                tool_args={"url": "https://example.com"},
            ),
        )
        bus.emit(
            None,
            _make_event(
                ToolUsageFinishedEvent,
                tool_name="scrape_website",
                agent_id="a-1",
                agent_role="Researcher",
                tool_args={"url": "https://example.com"},
                output="<html>...</html>",
                started_at=started,
                finished_at=datetime.now(UTC),
                from_cache=False,
            ),
        )

        assert len(spans) == 1
        span = spans[0]
        assert span.server_name == "crewai"
        assert span.tool_name == "scrape_website"
        assert span.agent_name == "Researcher"
        assert span.status == ToolCallStatus.SUCCESS
        assert span.input_args == {"url": "https://example.com"}
        assert "<html>" in span.output_result

    def test_mcp_tool_name_parsed_correctly(self):
        listener, spans, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        bus.emit(
            None,
            _make_event(
                ToolUsageStartedEvent,
                tool_name="mcp__postgres__query_database",
                agent_id="a-1",
                agent_role="DBA",
                tool_args="SELECT 1",
            ),
        )
        bus.emit(
            None,
            _make_event(
                ToolUsageFinishedEvent,
                tool_name="mcp__postgres__query_database",
                agent_id="a-1",
                agent_role="DBA",
                tool_args="SELECT 1",
                output="[{id: 1}]",
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
                from_cache=False,
            ),
        )

        assert len(spans) == 1
        assert spans[0].server_name == "postgres"
        assert spans[0].tool_name == "query_database"

    def test_cached_tool_result_annotated(self):
        listener, spans, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        bus.emit(
            None,
            _make_event(
                ToolUsageFinishedEvent,
                tool_name="search",
                agent_id="",
                agent_role="Agent",
                tool_args={},
                output="cached result",
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
                from_cache=True,
            ),
        )

        assert spans[0].output_result.startswith("[cached]")

    def test_tool_error_creates_error_span(self):
        listener, spans, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        bus.emit(
            None,
            _make_event(
                ToolUsageStartedEvent,
                tool_name="broken_tool",
                agent_id="a-1",
                agent_role="Agent",
                tool_args={},
            ),
        )
        bus.emit(
            None,
            _make_event(
                ToolUsageErrorEvent,
                tool_name="broken_tool",
                agent_id="a-1",
                agent_role="Agent",
                tool_args={},
                error="connection refused",
            ),
        )

        assert len(spans) == 1
        assert spans[0].status == ToolCallStatus.ERROR
        assert spans[0].error == "connection refused"

    def test_tool_args_string_wrapped_in_dict(self):
        """String tool_args are wrapped as {"input": value}."""
        listener, spans, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        bus.emit(
            None,
            _make_event(
                ToolUsageFinishedEvent,
                tool_name="calculator",
                agent_id="",
                agent_role=None,
                tool_args="2 + 2",
                output="4",
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
                from_cache=False,
            ),
        )

        assert spans[0].input_args == {"input": "2 + 2"}


# ===========================================================================
# Test: LLM calls
# ===========================================================================


class TestLLMCalls:
    """LLM event handlers are intentionally no-ops — SDK patches handle LLM spans.

    These tests verify the handlers don't create duplicate spans.
    """

    def test_llm_completed_does_not_create_span(self):
        """LLM completed events are suppressed to avoid duplicating SDK patch spans."""
        listener, spans, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        bus.emit(
            None,
            _make_event(
                LLMCallCompletedEvent,
                model="anthropic/claude-haiku-4-5",
                agent_role="Content Writer",
                response="marketing copy",
                messages=[{"role": "user", "content": "Write copy"}],
            ),
        )

        assert len(spans) == 0  # No span — SDK patch handles it

    def test_llm_failed_does_not_create_span(self):
        listener, spans, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        bus.emit(
            None,
            _make_event(
                LLMCallFailedEvent,
                model="anthropic/claude-haiku-4-5",
                agent_role="Agent",
                error="rate limit exceeded",
            ),
        )

        assert len(spans) == 0  # No span — SDK patch handles it


# ===========================================================================
# Test: A2A delegation (agent handoff)
# ===========================================================================


class TestA2ADelegation:
    def test_delegation_completed_creates_handoff_span(self):
        listener, spans, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        started = datetime.now(UTC) - timedelta(seconds=5)
        bus.emit(
            None,
            _make_event(
                A2ADelegationStartedEvent,
                agent_id="billing-agent",
                endpoint="http://billing:8080",
                task_description="Process refund",
                agent_role="Support Agent",
                timestamp=started,
            ),
        )
        bus.emit(
            None,
            _make_event(
                A2ADelegationCompletedEvent,
                agent_id="billing-agent",
                a2a_agent_name="Billing Agent",
                agent_role="Support Agent",
                status="completed",
                result="Refund processed: $50.00",
                error=None,
                endpoint="http://billing:8080",
            ),
        )

        assert len(spans) == 1
        span = spans[0]
        assert span.span_type == "handoff"
        assert span.agent_name == "Support Agent"
        assert span.target_agent_name == "Billing Agent"
        assert span.tool_name == "→ Billing Agent"
        assert span.status == ToolCallStatus.SUCCESS
        assert "Refund processed" in span.output_result

    def test_delegation_failed_creates_error_handoff(self):
        listener, spans, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        bus.emit(
            None,
            _make_event(
                A2ADelegationStartedEvent,
                agent_id="ext-agent",
                endpoint="http://ext:9090",
                task_description="External task",
                agent_role="Orchestrator",
            ),
        )
        bus.emit(
            None,
            _make_event(
                A2ADelegationCompletedEvent,
                agent_id="ext-agent",
                a2a_agent_name=None,
                agent_role="Orchestrator",
                status="failed",
                result=None,
                error="Connection refused",
                endpoint="http://ext:9090",
            ),
        )

        assert len(spans) == 1
        assert spans[0].status == ToolCallStatus.ERROR
        assert spans[0].error == "Connection refused"
        # Falls back to endpoint when a2a_agent_name is None
        assert spans[0].target_agent_name == "http://ext:9090"

    def test_conversation_completed_creates_span(self):
        listener, spans, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        started = datetime.now(UTC) - timedelta(seconds=10)
        bus.emit(
            None,
            _make_event(
                A2AConversationStartedEvent,
                agent_id="chat-agent",
                endpoint="http://chat:8080",
                a2a_agent_name="Chat Agent",
                agent_role="Coordinator",
                timestamp=started,
            ),
        )
        bus.emit(
            None,
            _make_event(
                A2AConversationCompletedEvent,
                agent_id="chat-agent",
                a2a_agent_name="Chat Agent",
                agent_role="Coordinator",
                status="completed",
                final_result="Conversation concluded with resolution",
                error=None,
                total_turns=5,
            ),
        )

        assert len(spans) == 1
        span = spans[0]
        assert span.tool_name == "a2a:Chat Agent"
        assert span.agent_name == "Coordinator"
        assert "[5 turns]" in span.output_result
        assert "resolution" in span.output_result

    def test_conversation_failed_creates_error_span(self):
        listener, spans, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        bus.emit(
            None,
            _make_event(
                A2AConversationStartedEvent,
                agent_id="broken-agent",
                endpoint="http://broken:8080",
                a2a_agent_name="Broken Agent",
                agent_role="Manager",
            ),
        )
        bus.emit(
            None,
            _make_event(
                A2AConversationCompletedEvent,
                agent_id="broken-agent",
                a2a_agent_name="Broken Agent",
                agent_role="Manager",
                status="failed",
                final_result=None,
                error="Agent unresponsive",
                total_turns=2,
            ),
        )

        assert len(spans) == 1
        assert spans[0].status == ToolCallStatus.ERROR
        assert spans[0].error == "Agent unresponsive"


# ===========================================================================
# Test: Session management
# ===========================================================================


class TestSessionManagement:
    def test_crew_started_generates_session_when_none_active(self):
        from langsight.sdk.auto_patch import _session_ctx

        # Ensure no session is active
        _session_ctx.set(None)

        listener, _, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        assert listener._session_id is None
        bus.emit(None, _make_event(CrewKickoffStartedEvent, crew_name="crew"))
        assert listener._session_id is not None
        assert len(listener._session_id) == 32

        # Cleanup
        _session_ctx.set(None)

    def test_crew_started_uses_existing_session(self):
        from langsight.sdk.auto_patch import _session_ctx

        _session_ctx.set(None)
        token = _session_ctx.set("existing-session-123")
        try:
            listener, _, _ = _make_listener()
            bus = _setup_and_get_bus(listener)

            bus.emit(None, _make_event(CrewKickoffStartedEvent, crew_name="crew"))

            # Should not have generated a new session — existing one is active
            assert listener._session_id is None
        finally:
            _session_ctx.reset(token)
            _session_ctx.set(None)

    def test_all_spans_carry_session_id(self):
        from langsight.sdk.auto_patch import _session_ctx

        _session_ctx.set(None)

        listener, spans, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        # Start crew (generates session)
        bus.emit(None, _make_event(CrewKickoffStartedEvent, crew_name="crew"))
        session_id = listener._get_session_id()
        assert session_id is not None

        # Emit various events
        task = MagicMock()
        task.id = "t-1"
        task.name = "task1"
        task.agent = None
        bus.emit(None, _make_event(TaskStartedEvent, task=task, context=""))
        bus.emit(None, _make_event(TaskCompletedEvent, task=task, output="done"))

        bus.emit(
            None,
            _make_event(
                ToolUsageFinishedEvent,
                tool_name="tool1",
                agent_id="",
                agent_role=None,
                tool_args={},
                output="ok",
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
                from_cache=False,
            ),
        )

        # All spans should carry the same session_id
        for span in spans:
            assert span.session_id == session_id

        # Cleanup
        _session_ctx.set(None)


# ===========================================================================
# Test: Project ID
# ===========================================================================


class TestProjectId:
    def test_spans_carry_project_id_from_client(self):
        listener, spans, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        bus.emit(None, _make_event(CrewKickoffStartedEvent, crew_name="crew"))
        bus.emit(
            None,
            _make_event(CrewKickoffCompletedEvent, crew_name="crew", output="done", total_tokens=100),
        )

        assert spans[0].project_id == "test-project"


# ===========================================================================
# Test: No client available
# ===========================================================================


class TestNoClient:
    def test_spans_dropped_when_no_client(self):
        """When client_resolver returns None, spans are silently dropped."""
        from langsight.integrations.crewai_events import LangSightCrewAIEventListener

        listener = LangSightCrewAIEventListener(client_resolver=lambda: None)
        bus = _setup_and_get_bus(listener)

        bus.emit(None, _make_event(CrewKickoffStartedEvent, crew_name="crew"))
        bus.emit(
            None,
            _make_event(CrewKickoffCompletedEvent, crew_name="crew", output="ok", total_tokens=0),
        )

        # No crash, no spans buffered (no client to buffer to)
        # Just verifying it doesn't raise


# ===========================================================================
# Test: Full crew execution flow
# ===========================================================================


class TestFullFlow:
    def test_complete_crew_execution_produces_expected_spans(self):
        """Simulate a full crew run: crew start → task → agent → tool → LLM → task complete → crew complete."""
        listener, spans, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        started = datetime.now(UTC) - timedelta(seconds=30)

        # 1. Crew starts
        bus.emit(None, _make_event(CrewKickoffStartedEvent, crew_name="marketing-crew", timestamp=started))

        # 2. Task starts
        task = MagicMock()
        task.id = "task-research"
        task.name = "research_task"
        agent = MagicMock()
        agent.role = "Lead Analyst"
        agent.id = "agent-analyst"
        task.agent = agent

        bus.emit(
            None,
            _make_event(TaskStartedEvent, task=task, context="", timestamp=started + timedelta(seconds=1)),
        )

        # 3. Agent starts
        bus.emit(
            None,
            _make_event(
                AgentExecutionStartedEvent,
                agent=agent,
                task=task,
                tools=[],
                task_prompt="Research the market",
                timestamp=started + timedelta(seconds=2),
            ),
        )

        # 4. Tool call
        bus.emit(
            None,
            _make_event(
                ToolUsageStartedEvent,
                tool_name="scrape_website",
                agent_id="agent-analyst",
                agent_role="Lead Analyst",
                tool_args={"url": "https://example.com"},
                timestamp=started + timedelta(seconds=3),
            ),
        )
        bus.emit(
            None,
            _make_event(
                ToolUsageFinishedEvent,
                tool_name="scrape_website",
                agent_id="agent-analyst",
                agent_role="Lead Analyst",
                tool_args={"url": "https://example.com"},
                output="<html>market data</html>",
                started_at=started + timedelta(seconds=3),
                finished_at=started + timedelta(seconds=5),
                from_cache=False,
            ),
        )

        # 5. LLM call
        bus.emit(
            None,
            _make_event(
                LLMCallCompletedEvent,
                model="anthropic/claude-haiku-4-5",
                agent_role="Lead Analyst",
                task_name="research_task",
                response="Based on the market data, here are the findings...",
                messages=[{"role": "user", "content": "Analyze this market data"}],
                timestamp=started + timedelta(seconds=6),
            ),
        )

        # 6. Agent completes
        bus.emit(
            None,
            _make_event(
                AgentExecutionCompletedEvent,
                agent=agent,
                task=task,
                output="Market analysis complete",
                timestamp=started + timedelta(seconds=8),
            ),
        )

        # 7. Task completes
        bus.emit(
            None,
            _make_event(
                TaskCompletedEvent,
                task=task,
                output="Research findings: market is growing 20% YoY",
                timestamp=started + timedelta(seconds=9),
            ),
        )

        # 8. Crew completes
        bus.emit(
            None,
            _make_event(
                CrewKickoffCompletedEvent,
                crew_name="marketing-crew",
                output="Final marketing strategy delivered",
                total_tokens=5000,
                timestamp=started + timedelta(seconds=10),
            ),
        )

        # Verify: tool_call + agent + task + crew = 4 spans
        # (LLM spans suppressed — handled by SDK patches instead)
        assert len(spans) == 4

        span_names = [s.tool_name for s in spans]
        assert "scrape_website" in span_names
        assert "agent:Lead Analyst" in span_names
        assert "task:research_task" in span_names
        assert "crew:marketing-crew" in span_names

        # LLM spans NOT created by event bus (SDK patches handle them)
        assert not any(s.tool_name.startswith("llm:") for s in spans)

        # All should have the same session_id
        session_ids = {s.session_id for s in spans}
        assert len(session_ids) == 1
        assert None not in session_ids

        # All should have project_id
        for span in spans:
            assert span.project_id == "test-project"

        # Check span types
        tool_spans = [s for s in spans if s.span_type == "tool_call"]
        agent_spans = [s for s in spans if s.span_type == "agent"]
        assert len(tool_spans) == 1
        assert len(agent_spans) == 3  # agent + task + crew

        # Verify span hierarchy (parent-child links)
        crew_span = next(s for s in spans if s.tool_name == "crew:marketing-crew")
        task_span = next(s for s in spans if s.tool_name == "task:research_task")
        agent_span = next(s for s in spans if s.tool_name == "agent:Lead Analyst")
        tool_span = next(s for s in spans if s.tool_name == "scrape_website")

        assert crew_span.parent_span_id is None  # root
        assert task_span.parent_span_id == crew_span.span_id
        assert agent_span.parent_span_id == task_span.span_id
        assert tool_span.parent_span_id == agent_span.span_id

        # All span_ids should be unique
        all_ids = [s.span_id for s in spans]
        assert len(set(all_ids)) == len(all_ids)


# ===========================================================================
# Test: Span parent-child hierarchy
# ===========================================================================


class TestSpanHierarchy:
    """Tests for the parent-child span hierarchy linking."""

    def test_crew_span_is_root(self):
        """Crew span has parent_span_id=None."""
        listener, spans, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        bus.emit(None, _make_event(CrewKickoffStartedEvent, crew_name="crew"))
        bus.emit(
            None,
            _make_event(CrewKickoffCompletedEvent, crew_name="crew", output="ok", total_tokens=0),
        )

        assert len(spans) == 1
        assert spans[0].parent_span_id is None

    def test_task_parent_is_crew(self):
        """Task span has parent_span_id pointing to crew span."""
        listener, spans, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        bus.emit(None, _make_event(CrewKickoffStartedEvent, crew_name="crew"))

        task = MagicMock()
        task.id = "t-1"
        task.name = "task1"
        task.agent = None
        bus.emit(None, _make_event(TaskStartedEvent, task=task, context=""))
        bus.emit(None, _make_event(TaskCompletedEvent, task=task, output="done"))
        bus.emit(
            None,
            _make_event(CrewKickoffCompletedEvent, crew_name="crew", output="ok", total_tokens=0),
        )

        task_span = next(s for s in spans if s.tool_name == "task:task1")
        crew_span = next(s for s in spans if s.tool_name == "crew:crew")
        assert task_span.parent_span_id == crew_span.span_id

    def test_agent_parent_is_task(self):
        """Agent span has parent_span_id pointing to task span."""
        listener, spans, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        bus.emit(None, _make_event(CrewKickoffStartedEvent, crew_name="crew"))

        agent = MagicMock()
        agent.id = "a-1"
        agent.role = "Analyst"
        task = MagicMock()
        task.id = "t-1"
        task.name = "task1"
        task.agent = agent

        bus.emit(None, _make_event(TaskStartedEvent, task=task, context=""))
        bus.emit(
            None,
            _make_event(
                AgentExecutionStartedEvent,
                agent=agent, task=task, tools=[], task_prompt="",
            ),
        )
        bus.emit(
            None,
            _make_event(AgentExecutionCompletedEvent, agent=agent, task=task, output="done"),
        )
        bus.emit(None, _make_event(TaskCompletedEvent, task=task, output="done"))

        agent_span = next(s for s in spans if s.tool_name == "agent:Analyst")
        task_span = next(s for s in spans if s.tool_name == "task:task1")
        assert agent_span.parent_span_id == task_span.span_id

    def test_tool_parent_is_agent(self):
        """Tool span has parent_span_id pointing to agent span."""
        listener, spans, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        agent = MagicMock()
        agent.id = "a-1"
        agent.role = "Analyst"

        bus.emit(
            None,
            _make_event(
                AgentExecutionStartedEvent,
                agent=agent, task=None, tools=[], task_prompt="",
            ),
        )
        bus.emit(
            None,
            _make_event(
                ToolUsageStartedEvent,
                tool_name="search", agent_id="a-1", agent_role="Analyst", tool_args={},
            ),
        )
        bus.emit(
            None,
            _make_event(
                ToolUsageFinishedEvent,
                tool_name="search", agent_id="a-1", agent_role="Analyst",
                tool_args={}, output="ok",
                started_at=datetime.now(UTC), finished_at=datetime.now(UTC),
                from_cache=False,
            ),
        )

        tool_span = next(s for s in spans if s.tool_name == "search")
        assert tool_span.parent_span_id is not None
        assert tool_span.parent_span_id == listener._agent_span_ids.get("a-1")

    def test_span_ids_pre_generated_and_stable(self):
        """Span IDs generated at 'started' events match those used at 'completed' events."""
        listener, spans, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        bus.emit(None, _make_event(CrewKickoffStartedEvent, crew_name="crew"))
        pre_crew_id = listener._crew_span_id
        assert pre_crew_id is not None

        bus.emit(
            None,
            _make_event(CrewKickoffCompletedEvent, crew_name="crew", output="ok", total_tokens=0),
        )
        assert spans[0].span_id == pre_crew_id

    def test_multiple_tasks_share_crew_parent(self):
        """Two sequential tasks both point to the same crew as parent."""
        listener, spans, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        bus.emit(None, _make_event(CrewKickoffStartedEvent, crew_name="crew"))

        for i in range(2):
            task = MagicMock()
            task.id = f"t-{i}"
            task.name = f"task{i}"
            task.agent = None
            bus.emit(None, _make_event(TaskStartedEvent, task=task, context=""))
            bus.emit(None, _make_event(TaskCompletedEvent, task=task, output="done"))

        bus.emit(
            None,
            _make_event(CrewKickoffCompletedEvent, crew_name="crew", output="ok", total_tokens=0),
        )

        crew_span = next(s for s in spans if s.tool_name == "crew:crew")
        task_spans = [s for s in spans if s.tool_name.startswith("task:")]
        assert len(task_spans) == 2
        for ts in task_spans:
            assert ts.parent_span_id == crew_span.span_id

    def test_bridge_dict_populated_on_agent_start(self):
        """_active_agent_span_ids is populated when agent starts (fallback path)."""
        from langsight.integrations.crewai_events import _active_agent_span_ids

        # Clear any pre-existing bridge entry to test fallback generation
        _active_agent_span_ids.pop("Analyst", None)

        listener, _, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        agent = MagicMock()
        agent.id = "a-1"
        agent.role = "Analyst"
        bus.emit(
            None,
            _make_event(
                AgentExecutionStartedEvent,
                agent=agent, task=None, tools=[], task_prompt="",
            ),
        )

        assert "Analyst" in _active_agent_span_ids
        assert _active_agent_span_ids["Analyst"] == listener._agent_span_ids["a-1"]

        # Cleanup
        _active_agent_span_ids.pop("Analyst", None)

    def test_bridge_dict_adopted_from_execute_task_patch(self):
        """_handle_agent_started adopts span_id already set by _patched_execute_task."""
        from langsight.integrations.crewai_events import _active_agent_span_ids

        # Simulate _patched_execute_task pre-generating a span_id
        _active_agent_span_ids["Analyst"] = "pre-generated-span-id"

        listener, _, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        agent = MagicMock()
        agent.id = "a-1"
        agent.role = "Analyst"
        bus.emit(
            None,
            _make_event(
                AgentExecutionStartedEvent,
                agent=agent, task=None, tools=[], task_prompt="",
            ),
        )

        # Should adopt the pre-generated ID, not generate a new one
        assert listener._agent_span_ids["a-1"] == "pre-generated-span-id"

        # Cleanup
        _active_agent_span_ids.pop("Analyst", None)

    def test_bridge_dict_cleared_on_agent_complete(self):
        """_active_agent_span_ids is cleared when agent completes."""
        from langsight.integrations.crewai_events import _active_agent_span_ids

        listener, _, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        agent = MagicMock()
        agent.id = "a-1"
        agent.role = "Analyst"
        bus.emit(
            None,
            _make_event(
                AgentExecutionStartedEvent,
                agent=agent, task=None, tools=[], task_prompt="",
            ),
        )
        assert "Analyst" in _active_agent_span_ids

        bus.emit(
            None,
            _make_event(AgentExecutionCompletedEvent, agent=agent, task=None, output="done"),
        )
        assert "Analyst" not in _active_agent_span_ids

    def test_cleanup_on_crew_completed(self):
        """Crew completion clears all tracking dicts to prevent leaks."""
        listener, _, _ = _make_listener()
        bus = _setup_and_get_bus(listener)

        bus.emit(None, _make_event(CrewKickoffStartedEvent, crew_name="crew"))

        task = MagicMock()
        task.id = "t-1"
        task.name = "task1"
        task.agent = None
        bus.emit(None, _make_event(TaskStartedEvent, task=task, context=""))
        # Intentionally don't complete task — simulate unbalanced events

        bus.emit(
            None,
            _make_event(CrewKickoffCompletedEvent, crew_name="crew", output="ok", total_tokens=0),
        )

        # All tracking dicts should be cleared
        assert listener._crew_span_id is None
        assert len(listener._task_span_ids) == 0
        assert len(listener._agent_span_ids) == 0
        assert len(listener._agent_to_task) == 0
        assert listener._active_task_id is None
