"""Unit tests for replay/engine.py — ReplayEngine and ReplayResult.

All tests are pure-unit: storage is replaced by MagicMock / AsyncMock.
No network, no MCP servers, no database, no Docker required.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from langsight.replay.engine import (
    DEFAULT_TIMEOUT_PER_CALL,
    DEFAULT_TOTAL_TIMEOUT,
    ReplayEngine,
    ReplayResult,
)
from langsight.sdk.models import ToolCallStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _span(
    span_type: str = "tool_call",
    input_json: str | None = '{"sql": "SELECT 1"}',
    server_name: str = "pg-mcp",
    tool_name: str = "query",
    span_id: str = "span-abc",
    trace_id: str = "trace-001",
    agent_name: str = "analyst",
) -> dict:
    return {
        "span_type": span_type,
        "input_json": input_json,
        "server_name": server_name,
        "tool_name": tool_name,
        "span_id": span_id,
        "trace_id": trace_id,
        "agent_name": agent_name,
    }


def _make_config(server_name: str = "pg-mcp") -> MagicMock:
    """Build a minimal LangSightConfig mock with one stdio server."""
    server = MagicMock()
    server.name = server_name
    server.transport = MagicMock()
    server.transport.value = "stdio"
    server.command = "python"
    server.args = []
    server.env = {}

    config = MagicMock()
    config.servers = [server]
    return config


def _make_storage(spans: list[dict] | None = None) -> MagicMock:
    storage = MagicMock()
    storage.get_session_trace = AsyncMock(return_value=spans or [])
    storage.save_tool_call_spans = AsyncMock()
    return storage


# ---------------------------------------------------------------------------
# ReplayResult
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestReplayResult:
    def test_to_dict_has_all_keys(self) -> None:
        result = ReplayResult(
            original_session_id="orig-001",
            replay_session_id="repl-002",
            total_spans=5,
            replayed=3,
            skipped=2,
            failed=1,
            duration_ms=123.456,
        )
        d = result.to_dict()
        assert set(d.keys()) == {
            "original_session_id",
            "replay_session_id",
            "total_spans",
            "replayed",
            "skipped",
            "failed",
            "duration_ms",
        }

    def test_to_dict_rounds_duration(self) -> None:
        result = ReplayResult(
            original_session_id="x",
            replay_session_id="y",
            total_spans=1,
            replayed=1,
            skipped=0,
            failed=0,
            duration_ms=99.9999,
        )
        assert result.to_dict()["duration_ms"] == round(99.9999, 2)

    def test_to_dict_preserves_string_fields(self) -> None:
        result = ReplayResult(
            original_session_id="orig",
            replay_session_id="repl",
            total_spans=0,
            replayed=0,
            skipped=0,
            failed=0,
            duration_ms=0.0,
        )
        d = result.to_dict()
        assert d["original_session_id"] == "orig"
        assert d["replay_session_id"] == "repl"

    def test_to_dict_counts_are_integers(self) -> None:
        result = ReplayResult(
            original_session_id="a",
            replay_session_id="b",
            total_spans=10,
            replayed=7,
            skipped=3,
            failed=2,
            duration_ms=50.0,
        )
        d = result.to_dict()
        assert d["total_spans"] == 10
        assert d["replayed"] == 7
        assert d["skipped"] == 3
        assert d["failed"] == 2


# ---------------------------------------------------------------------------
# ReplayEngine — constructor and guard clauses
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestReplayEngineInit:
    async def test_requires_clickhouse_backend(self) -> None:
        """Storage without get_session_trace raises RuntimeError immediately."""
        storage = MagicMock(spec=[])  # no attributes
        engine = ReplayEngine(storage, _make_config())
        with pytest.raises(RuntimeError, match="ClickHouse backend"):
            await engine.replay("sess-001")

    async def test_raises_when_session_not_found(self) -> None:
        storage = _make_storage(spans=[])  # empty trace
        engine = ReplayEngine(storage, _make_config())
        with pytest.raises(ValueError, match="not found or has no spans"):
            await engine.replay("missing-session")

    def test_default_timeouts(self) -> None:
        engine = ReplayEngine(_make_storage(), _make_config())
        assert engine._timeout_per_call == DEFAULT_TIMEOUT_PER_CALL
        assert engine._total_timeout == DEFAULT_TOTAL_TIMEOUT

    def test_custom_timeouts(self) -> None:
        engine = ReplayEngine(
            _make_storage(),
            _make_config(),
            timeout_per_call=5.0,
            total_timeout=30.0,
        )
        assert engine._timeout_per_call == 5.0
        assert engine._total_timeout == 30.0


# ---------------------------------------------------------------------------
# ReplayEngine.replay — happy path
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestReplayEngineReplay:
    async def test_skips_non_tool_call_spans(self) -> None:
        """Agent spans (span_type=agent) must be counted as skipped, not replayed."""
        spans = [
            _span(span_type="agent", input_json=None),
            _span(span_type="agent", input_json='{"q": "hi"}'),
        ]
        storage = _make_storage(spans=spans)
        engine = ReplayEngine(storage, _make_config())

        with patch.object(engine, "_replay_one", new_callable=AsyncMock) as mock_one:
            result = await engine.replay("sess-001")

        mock_one.assert_not_called()
        assert result.skipped == 2
        assert result.replayed == 0
        assert result.total_spans == 2

    async def test_skips_spans_without_input_json(self) -> None:
        """tool_call spans with no input_json are skipped (nothing to replay)."""
        spans = [_span(span_type="tool_call", input_json=None)]
        storage = _make_storage(spans=spans)
        engine = ReplayEngine(storage, _make_config())

        with patch.object(engine, "_replay_one", new_callable=AsyncMock) as mock_one:
            result = await engine.replay("sess-001")

        mock_one.assert_not_called()
        assert result.skipped == 1
        assert result.replayed == 0

    async def test_replay_calls_save_tool_call_spans(self) -> None:
        """Successful replay spans must be forwarded to storage.save_tool_call_spans."""
        spans = [_span()]
        storage = _make_storage(spans=spans)
        engine = ReplayEngine(storage, _make_config())

        fake_span = MagicMock()
        fake_span.status = ToolCallStatus.SUCCESS

        with patch.object(engine, "_replay_one", new_callable=AsyncMock, return_value=fake_span):
            result = await engine.replay("sess-001")

        storage.save_tool_call_spans.assert_called_once()
        assert result.replayed == 1
        assert result.failed == 0

    async def test_failed_replay_span_increments_failed_count(self) -> None:
        """Spans with status != SUCCESS must increment the failed counter."""
        spans = [_span()]
        storage = _make_storage(spans=spans)
        engine = ReplayEngine(storage, _make_config())

        fake_span = MagicMock()
        fake_span.status = ToolCallStatus.ERROR

        with patch.object(engine, "_replay_one", new_callable=AsyncMock, return_value=fake_span):
            result = await engine.replay("sess-001")

        assert result.failed == 1
        assert result.replayed == 1  # replayed means attempted, failed is separate

    async def test_replay_session_id_is_unique_per_call(self) -> None:
        """Each call to replay() must generate a distinct replay_session_id."""
        spans = [_span()]
        storage = _make_storage(spans=spans)
        engine = ReplayEngine(storage, _make_config())

        fake_span = MagicMock()
        fake_span.status = ToolCallStatus.SUCCESS

        with patch.object(engine, "_replay_one", new_callable=AsyncMock, return_value=fake_span):
            result1 = await engine.replay("sess-001")
            result2 = await engine.replay("sess-001")

        assert result1.replay_session_id != result2.replay_session_id

    async def test_no_save_when_no_replay_spans(self) -> None:
        """save_tool_call_spans must NOT be called when all spans are skipped."""
        spans = [_span(span_type="agent", input_json=None)]
        storage = _make_storage(spans=spans)
        engine = ReplayEngine(storage, _make_config())

        with patch.object(engine, "_replay_one", new_callable=AsyncMock) as mock_one:
            await engine.replay("sess-001")

        mock_one.assert_not_called()
        storage.save_tool_call_spans.assert_not_called()

    async def test_total_timeout_cuts_replay_short(self) -> None:
        """When total_timeout fires, already-replayed spans must still be saved."""
        spans = [_span(span_id=f"sp-{i}") for i in range(5)]
        storage = _make_storage(spans=spans)
        engine = ReplayEngine(storage, _make_config(), total_timeout=0.001)

        fake_span = MagicMock()
        fake_span.status = ToolCallStatus.SUCCESS

        async def slow_replay(*args, **kwargs):
            await asyncio.sleep(1)
            return fake_span

        with patch.object(engine, "_replay_one", side_effect=slow_replay):
            result = await engine.replay("sess-001")

        # Some spans may have been attempted (possibly 0 given tiny timeout)
        # but the function must return a valid ReplayResult without raising
        assert result.original_session_id == "sess-001"
        assert result.total_spans == 5
        assert isinstance(result.duration_ms, float)

    async def test_original_session_id_preserved_in_result(self) -> None:
        spans = [_span()]
        storage = _make_storage(spans=spans)
        engine = ReplayEngine(storage, _make_config())

        fake_span = MagicMock()
        fake_span.status = ToolCallStatus.SUCCESS

        with patch.object(engine, "_replay_one", new_callable=AsyncMock, return_value=fake_span):
            result = await engine.replay("my-session-xyz")

        assert result.original_session_id == "my-session-xyz"

    async def test_project_id_forwarded_to_get_session_trace(self) -> None:
        """project_id passed to replay() must be forwarded to get_session_trace."""
        storage = _make_storage(spans=[_span()])
        engine = ReplayEngine(storage, _make_config())

        fake_span = MagicMock()
        fake_span.status = ToolCallStatus.SUCCESS

        with patch.object(engine, "_replay_one", new_callable=AsyncMock, return_value=fake_span):
            await engine.replay("sess-001", project_id="proj-abc")

        storage.get_session_trace.assert_called_once_with("sess-001", project_id="proj-abc")


# ---------------------------------------------------------------------------
# ReplayEngine._replay_one — error handling
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestReplayOneErrorHandling:
    async def test_returns_error_span_when_server_not_in_config(self) -> None:
        """If the server is not in config, the span status must be ERROR."""
        original = _span(server_name="unknown-server")
        storage = _make_storage()
        # Config has no server named "unknown-server"
        engine = ReplayEngine(storage, _make_config(server_name="other-server"))

        span = await engine._replay_one(original=original, replay_session_id="repl-001")

        assert span.status == ToolCallStatus.ERROR
        assert "not found in config" in (span.error or "")

    async def test_returns_timeout_span_on_call_timeout(self) -> None:
        """asyncio.wait_for timeout must produce status=TIMEOUT on the span."""
        original = _span()
        storage = _make_storage()
        engine = ReplayEngine(storage, _make_config(), timeout_per_call=0.001)

        async def slow_tool(*args, **kwargs):
            await asyncio.sleep(10)
            return "result"

        with patch.object(engine, "_call_tool", side_effect=slow_tool):
            span = await engine._replay_one(original=original, replay_session_id="repl-001")

        assert span.status == ToolCallStatus.TIMEOUT
        assert "timed out" in (span.error or "").lower()

    async def test_returns_error_span_on_call_exception(self) -> None:
        """Any non-timeout exception in _call_tool must produce status=ERROR."""
        original = _span()
        storage = _make_storage()
        engine = ReplayEngine(storage, _make_config())

        with patch.object(
            engine, "_call_tool", new_callable=AsyncMock,
            side_effect=RuntimeError("boom")
        ):
            span = await engine._replay_one(original=original, replay_session_id="repl-001")

        assert span.status == ToolCallStatus.ERROR
        assert "boom" in (span.error or "")

    async def test_span_preserves_trace_id_from_original(self) -> None:
        """The replay span must carry the trace_id from the original span."""
        original = _span(trace_id="trace-xyz")
        storage = _make_storage()
        engine = ReplayEngine(storage, _make_config())

        with patch.object(
            engine, "_call_tool", new_callable=AsyncMock, return_value='{"ok": true}'
        ):
            span = await engine._replay_one(original=original, replay_session_id="repl-001")

        assert span.trace_id == "trace-xyz"

    async def test_span_sets_replay_of_to_original_span_id(self) -> None:
        """replay_of on the new span must point to the original span_id."""
        original = _span(span_id="original-span-id")
        storage = _make_storage()
        engine = ReplayEngine(storage, _make_config())

        with patch.object(
            engine, "_call_tool", new_callable=AsyncMock, return_value='{"ok": true}'
        ):
            span = await engine._replay_one(original=original, replay_session_id="repl-001")

        assert span.replay_of == "original-span-id"

    async def test_malformed_input_json_does_not_crash(self) -> None:
        """If input_json is not valid JSON, args defaults to None and replay continues."""
        original = _span(input_json="not-valid-json{{")
        storage = _make_storage()
        engine = ReplayEngine(storage, _make_config())

        with patch.object(
            engine, "_call_tool", new_callable=AsyncMock, return_value="result"
        ) as mock_call:
            span = await engine._replay_one(original=original, replay_session_id="repl-001")

        # _call_tool was called with empty dict as fallback for None args
        mock_call.assert_called_once()
        call_args = mock_call.call_args[0]
        # Third positional arg is `arguments`
        assert call_args[2] == {}
        assert span.status == ToolCallStatus.SUCCESS


# ---------------------------------------------------------------------------
# ReplayEngine._call_tool — dispatch logic
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCallToolDispatch:
    async def test_raises_for_unsupported_transport(self) -> None:
        """An unsupported transport value must raise ValueError."""
        server_config = MagicMock()
        server_config.name = "my-server"
        server_config.transport = MagicMock()
        server_config.transport.value = "grpc"  # unsupported

        engine = ReplayEngine(_make_storage(), _make_config())

        with pytest.raises(ValueError, match="Unsupported transport"):
            await engine._call_tool(server_config, "my_tool", {})

    async def test_raises_for_stdio_with_no_command(self) -> None:
        """stdio server without a command must raise ValueError."""
        server_config = MagicMock()
        server_config.name = "my-server"
        server_config.transport = MagicMock()
        server_config.transport.value = "stdio"
        server_config.command = None

        engine = ReplayEngine(_make_storage(), _make_config())

        with pytest.raises(ValueError, match="no command configured"):
            await engine._call_tool(server_config, "my_tool", {})

    async def test_raises_for_http_with_no_url(self) -> None:
        """SSE/HTTP server without a URL must raise ValueError."""
        server_config = MagicMock()
        server_config.name = "my-server"
        server_config.transport = MagicMock()
        server_config.transport.value = "sse"
        server_config.url = None

        engine = ReplayEngine(_make_storage(), _make_config())

        with pytest.raises(ValueError, match="no URL configured"):
            await engine._call_tool(server_config, "my_tool", {})
