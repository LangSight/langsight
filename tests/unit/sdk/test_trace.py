"""Unit tests for sdk/trace.py — AgentTrace, trace(), _NoopTrace.

All tests are pure-unit. The LangSightClient is replaced by a minimal stub
so that buffer_span() can be inspected without any network calls.

asyncio_mode = "auto" is set project-wide in pyproject.toml, so no
@pytest.mark.asyncio is needed on individual async test methods.
"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any

import pytest

from langsight.sdk.models import ToolCallStatus
from langsight.sdk.trace import AgentTrace, _NoopTrace, trace


# ---------------------------------------------------------------------------
# Minimal client stub — avoids importing LangSightClient (heavy deps)
# ---------------------------------------------------------------------------


class _StubClient:
    """Captures buffer_span() calls for assertion without any network activity."""

    def __init__(self) -> None:
        self.spans: deque = deque()
        self._project_id: str | None = "test-project"

    def buffer_span(self, span: Any) -> None:
        self.spans.append(span)


# ---------------------------------------------------------------------------
# AgentTrace — set_output
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAgentTraceSetOutput:
    def _make_trace(self) -> AgentTrace:
        return AgentTrace(
            client=_StubClient(),
            agent_name="analyst",
            session_id="sess-001",
            trace_id="trace-001",
            project_id="proj-001",
        )

    def test_set_output_stores_string(self) -> None:
        t = self._make_trace()
        t.set_output("hello world")
        assert t._output == "hello world"

    def test_set_output_converts_non_string_to_str(self) -> None:
        t = self._make_trace()
        t.set_output(42)
        assert t._output == "42"

    def test_set_output_with_none_clears_output(self) -> None:
        t = self._make_trace()
        t.set_output("something")
        t.set_output(None)
        assert t._output is None

    def test_set_output_fail_open_on_error(self) -> None:
        """set_output must never raise — even if str() fails."""

        class Unstrifiable:
            def __str__(self):
                raise RuntimeError("cannot stringify")

        t = self._make_trace()
        # Must not raise
        t.set_output(Unstrifiable())


# ---------------------------------------------------------------------------
# AgentTrace — async context manager
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAgentTraceAsyncContextManager:
    def _make(
        self, agent_name: str = "analyst", session_id: str = "sess-001"
    ) -> tuple[AgentTrace, _StubClient]:
        client = _StubClient()
        t = AgentTrace(
            client=client,
            agent_name=agent_name,
            session_id=session_id,
            trace_id=None,
            project_id=None,
        )
        return t, client

    async def test_success_path_emits_success_span(self) -> None:
        t, client = self._make()
        async with t:
            pass  # no exception
        assert len(client.spans) == 1
        assert client.spans[0].status == ToolCallStatus.SUCCESS

    async def test_exception_path_emits_error_span(self) -> None:
        t, client = self._make()
        with pytest.raises(ValueError):
            async with t:
                raise ValueError("something broke")
        assert len(client.spans) == 1
        assert client.spans[0].status == ToolCallStatus.ERROR
        assert "ValueError" in (client.spans[0].error or "")

    async def test_timeout_exception_emits_timeout_span(self) -> None:
        t, client = self._make()
        with pytest.raises(TimeoutError):
            async with t:
                raise TimeoutError("took too long")
        assert len(client.spans) == 1
        assert client.spans[0].status == ToolCallStatus.TIMEOUT

    async def test_cancelled_error_emits_timeout_span(self) -> None:
        t, client = self._make()
        with pytest.raises(asyncio.CancelledError):
            async with t:
                raise asyncio.CancelledError()
        assert len(client.spans) == 1
        assert client.spans[0].status == ToolCallStatus.TIMEOUT

    async def test_does_not_suppress_exceptions(self) -> None:
        """__aexit__ must return False — exceptions must always propagate."""
        t, _ = self._make()
        exc_propagated = False
        try:
            async with t:
                raise RuntimeError("must propagate")
        except RuntimeError:
            exc_propagated = True
        assert exc_propagated

    async def test_span_carries_agent_name(self) -> None:
        t, client = self._make(agent_name="my-agent")
        async with t:
            pass
        assert client.spans[0].agent_name == "my-agent"

    async def test_span_carries_session_id(self) -> None:
        t, client = self._make(session_id="sess-xyz")
        async with t:
            pass
        assert client.spans[0].session_id == "sess-xyz"

    async def test_span_type_is_agent(self) -> None:
        t, client = self._make()
        async with t:
            pass
        assert client.spans[0].span_type == "agent"

    async def test_output_stored_in_span(self) -> None:
        t, client = self._make()
        async with t as trace_ctx:
            trace_ctx.set_output("the final answer")
        assert client.spans[0].output_result == "the final answer"


# ---------------------------------------------------------------------------
# AgentTrace — sync context manager
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAgentTraceSyncContextManager:
    def _make(self) -> tuple[AgentTrace, _StubClient]:
        client = _StubClient()
        t = AgentTrace(
            client=client,
            agent_name="sync-agent",
            session_id="sess-002",
            trace_id=None,
            project_id=None,
        )
        return t, client

    def test_sync_success_emits_success_span(self) -> None:
        t, client = self._make()
        with t:
            pass
        assert len(client.spans) == 1
        assert client.spans[0].status == ToolCallStatus.SUCCESS

    def test_sync_exception_emits_error_span(self) -> None:
        t, client = self._make()
        with pytest.raises(ValueError):
            with t:
                raise ValueError("sync broke")
        assert len(client.spans) == 1
        assert client.spans[0].status == ToolCallStatus.ERROR

    def test_sync_timeout_emits_timeout_span(self) -> None:
        t, client = self._make()
        with pytest.raises(TimeoutError):
            with t:
                raise TimeoutError("sync timeout")
        assert client.spans[0].status == ToolCallStatus.TIMEOUT

    def test_sync_does_not_suppress_exceptions(self) -> None:
        t, _ = self._make()
        exc_propagated = False
        try:
            with t:
                raise RuntimeError("sync propagate")
        except RuntimeError:
            exc_propagated = True
        assert exc_propagated


# ---------------------------------------------------------------------------
# trace() — context manager mode (no client → NoopTrace)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTraceContextManagerNoClient:
    def test_returns_noop_when_no_client_configured(self) -> None:
        """With no global client and no explicit client, trace() returns _NoopTrace."""
        import sys
        ap = sys.modules["langsight.sdk.auto_patch"]
        original = ap._global_client
        try:
            ap._global_client = None
            result = trace(agent_name="my-agent")
            assert isinstance(result, _NoopTrace)
        finally:
            ap._global_client = original

    async def test_noop_trace_async_is_no_op(self) -> None:
        t = _NoopTrace()
        async with t as ctx:
            ctx.set_output("ignored")  # must not raise

    def test_noop_trace_sync_is_no_op(self) -> None:
        t = _NoopTrace()
        with t as ctx:
            ctx.set_output("ignored")  # must not raise

    async def test_noop_trace_does_not_suppress_exceptions(self) -> None:
        t = _NoopTrace()
        exc_propagated = False
        try:
            async with t:
                raise RuntimeError("should propagate through noop")
        except RuntimeError:
            exc_propagated = True
        assert exc_propagated

    def test_noop_trace_set_output_is_no_op(self) -> None:
        t = _NoopTrace()
        # Must not raise
        t.set_output("anything")
        t.set_output(None)
        t.set_output(42)


# ---------------------------------------------------------------------------
# trace() — decorator mode
# ---------------------------------------------------------------------------
# trace() decorator mode requires passing the callable as the first positional
# argument: trace(func, *, client=..., agent_name=...).
# The @trace(agent_name="x") pattern is for context manager mode only.
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTraceDecorator:
    async def test_decorator_with_explicit_client_emits_span(self) -> None:
        client = _StubClient()

        async def my_agent() -> str:
            return "done"

        wrapped = trace(my_agent, client=client, agent_name="decorated")
        result = await wrapped()
        assert result == "done"
        assert len(client.spans) == 1
        assert client.spans[0].status == ToolCallStatus.SUCCESS
        assert client.spans[0].agent_name == "decorated"

    async def test_decorator_records_output(self) -> None:
        client = _StubClient()

        async def my_agent() -> str:
            return "the answer"

        wrapped = trace(my_agent, client=client, agent_name="output-agent")
        await wrapped()
        assert client.spans[0].output_result == "the answer"

    async def test_decorator_records_error_on_exception(self) -> None:
        client = _StubClient()

        async def my_agent() -> None:
            raise ValueError("intentional")

        wrapped = trace(my_agent, client=client, agent_name="failing-agent")
        with pytest.raises(ValueError):
            await wrapped()

        assert client.spans[0].status == ToolCallStatus.ERROR
        assert "intentional" in (client.spans[0].error or "")

    async def test_decorator_uses_function_name_as_agent_name_by_default(self) -> None:
        client = _StubClient()

        async def my_special_agent() -> None:
            pass

        wrapped = trace(my_special_agent, client=client)
        await wrapped()
        assert client.spans[0].agent_name == "my_special_agent"

    async def test_decorator_preserves_function_metadata(self) -> None:
        """@functools.wraps must preserve __name__ and __doc__."""
        client = _StubClient()

        async def documented_agent() -> None:
            """I have a docstring."""

        wrapped = trace(documented_agent, client=client)
        assert wrapped.__name__ == "documented_agent"
        assert wrapped.__doc__ == "I have a docstring."

    async def test_bare_decorator_without_client_uses_noop(self) -> None:
        """trace(func) with no client and no global client must not raise."""
        import sys
        ap = sys.modules["langsight.sdk.auto_patch"]
        original = ap._global_client
        try:
            ap._global_client = None

            async def bare_agent() -> str:
                return "ok"

            wrapped = trace(bare_agent)
            result = await wrapped()
            assert result == "ok"
        finally:
            ap._global_client = original

    def test_trace_raises_typeerror_for_non_callable(self) -> None:
        with pytest.raises(TypeError, match="expected a callable or None"):
            trace(42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# trace() — context manager with explicit client
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTraceContextManagerWithClient:
    async def test_emits_span_on_success(self) -> None:
        client = _StubClient()
        async with trace(client=client, agent_name="ctx-agent", session_id="s-1") as t:
            t.set_output("ctx result")
        assert len(client.spans) == 1
        assert client.spans[0].status == ToolCallStatus.SUCCESS
        assert client.spans[0].output_result == "ctx result"
        assert client.spans[0].session_id == "s-1"

    async def test_emits_error_span_on_exception(self) -> None:
        client = _StubClient()
        with pytest.raises(RuntimeError):
            async with trace(client=client, agent_name="ctx-agent"):
                raise RuntimeError("ctx error")
        assert client.spans[0].status == ToolCallStatus.ERROR

    async def test_agent_name_defaults_to_none_value_in_span(self) -> None:
        """When agent_name is None, span server_name defaults to 'agent'."""
        client = _StubClient()
        async with trace(client=client):
            pass
        # server_name is 'agent' when agent_name is None (see _finish logic)
        assert client.spans[0].server_name == "agent"
