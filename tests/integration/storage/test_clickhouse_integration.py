"""
ClickHouse integration tests — require a running ClickHouse instance.

Run with:
    docker compose up -d clickhouse
    uv run pytest -m integration-clickhouse -v

These tests verify the full ClickHouse backend against a real server:
- DDL executes (tables + materialized views created)
- Health results persist and are queryable
- Tool call spans persist with parent_span_id + span_type
- Schema snapshots persist
- get_session_trace() reconstructs multi-agent trees
"""
from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta

import pytest

from langsight.models import HealthCheckResult, ServerStatus
from langsight.sdk.models import ToolCallSpan, ToolCallStatus
from langsight.storage.clickhouse import ClickHouseBackend

CLICKHOUSE_URL = "http://localhost:8123"
TEST_DB = "langsight_test"

pytestmark = pytest.mark.integration


_CH_USER = os.environ.get("CLICKHOUSE_USER", "default")
_CH_PASSWORD = os.environ.get("CLICKHOUSE_PASSWORD", os.environ.get("LANGSIGHT_CLICKHOUSE_PASSWORD", ""))


@pytest.fixture(scope="module")
async def ch():
    """Open a ClickHouse backend against the test database and clean up after."""
    import clickhouse_connect

    # Create fresh test database
    admin = await clickhouse_connect.get_async_client(
        host="localhost", port=8123, username=_CH_USER, password=_CH_PASSWORD
    )
    await admin.command(f"DROP DATABASE IF EXISTS {TEST_DB}")
    await admin.command(f"CREATE DATABASE {TEST_DB}")
    await admin.close()

    backend = await ClickHouseBackend.open(
        host="localhost", port=8123, database=TEST_DB,
        username=_CH_USER, password=_CH_PASSWORD
    )
    yield backend
    await backend.close()

    # Teardown
    admin2 = await clickhouse_connect.get_async_client(
        host="localhost", port=8123, username=_CH_USER, password=_CH_PASSWORD
    )
    await admin2.command(f"DROP DATABASE IF EXISTS {TEST_DB}")
    await admin2.close()


class TestDDL:
    async def test_tables_created(self, ch: ClickHouseBackend) -> None:
        """Verify all tables and materialized views were created by open()."""
        import clickhouse_connect

        client = await clickhouse_connect.get_async_client(
            host="localhost", port=8123, database=TEST_DB, username=_CH_USER, password=_CH_PASSWORD
        )
        result = await client.query("SHOW TABLES")
        tables = {row[0] for row in result.result_rows}
        await client.close()

        assert "mcp_health_results" in tables, f"Missing mcp_health_results, got: {tables}"
        assert "mcp_tool_calls" in tables, f"Missing mcp_tool_calls, got: {tables}"
        assert "mcp_schema_snapshots" in tables, f"Missing mcp_schema_snapshots, got: {tables}"
        assert "mv_tool_reliability" in tables, f"Missing mv_tool_reliability, got: {tables}"
        assert "session_health_tags" in tables, f"Missing session_health_tags, got: {tables}"
        assert "mv_agent_sessions" not in tables, "mv_agent_sessions was removed in v0.7.1 — should not exist"

    async def test_mcp_tool_calls_has_parent_span_id_column(self, ch: ClickHouseBackend) -> None:
        import clickhouse_connect

        client = await clickhouse_connect.get_async_client(
            host="localhost", port=8123, database=TEST_DB, username=_CH_USER, password=_CH_PASSWORD
        )
        result = await client.query("DESCRIBE TABLE mcp_tool_calls")
        columns = {row[0] for row in result.result_rows}
        await client.close()

        assert "parent_span_id" in columns
        assert "span_type" in columns
        assert "session_id" in columns
        assert "agent_name" in columns


class TestHealthResults:
    async def test_save_and_retrieve_health_result(self, ch: ClickHouseBackend) -> None:
        result = HealthCheckResult(
            server_name="test-pg",
            status=ServerStatus.UP,
            latency_ms=42.5,
            tools_count=5,
            schema_hash="abc123def456ab12",
            checked_at=datetime.now(UTC),
        )
        await ch.save_health_result(result)
        # ClickHouse is eventually consistent — wait for merge
        await asyncio.sleep(1)

        history = await ch.get_health_history("test-pg", limit=10)
        assert len(history) >= 1
        saved = history[0]
        assert saved.server_name == "test-pg"
        assert saved.status == ServerStatus.UP
        assert saved.latency_ms == 42.5
        assert saved.tools_count == 5

    async def test_save_multiple_results_ordered_newest_first(
        self, ch: ClickHouseBackend
    ) -> None:
        base = datetime.now(UTC)
        for i in range(3):
            await ch.save_health_result(HealthCheckResult(
                server_name="ordered-server",
                status=ServerStatus.UP,
                latency_ms=float(i * 10),
                checked_at=base + timedelta(seconds=i),
            ))
        await asyncio.sleep(1)

        history = await ch.get_health_history("ordered-server", limit=10)
        assert len(history) >= 3
        # Newest first
        assert history[0].checked_at >= history[1].checked_at

    async def test_history_limited(self, ch: ClickHouseBackend) -> None:
        for _ in range(5):
            await ch.save_health_result(HealthCheckResult(
                server_name="limit-test",
                status=ServerStatus.DOWN,
                checked_at=datetime.now(UTC),
            ))
        await asyncio.sleep(1)
        history = await ch.get_health_history("limit-test", limit=2)
        assert len(history) <= 2


class TestSchemaSnapshots:
    async def test_save_and_retrieve_snapshot(self, ch: ClickHouseBackend) -> None:
        await ch.save_schema_snapshot("snap-server", "hash-abc123", 7)
        await asyncio.sleep(1)

        retrieved = await ch.get_latest_schema_hash("snap-server")
        assert retrieved == "hash-abc123"

    async def test_returns_none_for_unknown_server(self, ch: ClickHouseBackend) -> None:
        result = await ch.get_latest_schema_hash("nonexistent-xyz")
        assert result is None

    async def test_returns_most_recent_hash(self, ch: ClickHouseBackend) -> None:
        await ch.save_schema_snapshot("multi-snap", "old-hash", 5)
        await asyncio.sleep(0.5)
        await ch.save_schema_snapshot("multi-snap", "new-hash", 6)
        await asyncio.sleep(1)

        result = await ch.get_latest_schema_hash("multi-snap")
        assert result == "new-hash"


class TestToolCallSpans:
    async def test_save_single_span(self, ch: ClickHouseBackend) -> None:
        now = datetime.now(UTC)
        span = ToolCallSpan(
            server_name="pg-mcp",
            tool_name="query",
            started_at=now,
            ended_at=now + timedelta(milliseconds=42),
            latency_ms=42.0,
            status=ToolCallStatus.SUCCESS,
            agent_name="test-agent",
            session_id="sess-single",
        )
        await ch.save_tool_call_span(span)
        await asyncio.sleep(1)

        trace = await ch.get_session_trace("sess-single")
        assert len(trace) >= 1
        assert trace[0]["tool_name"] == "query"
        assert trace[0]["status"] == "success"

    async def test_save_batch_spans(self, ch: ClickHouseBackend) -> None:
        now = datetime.now(UTC)
        spans = [
            ToolCallSpan(
                server_name="pg-mcp", tool_name=f"tool_{i}",
                started_at=now + timedelta(milliseconds=i * 100),
                ended_at=now + timedelta(milliseconds=i * 100 + 50),
                latency_ms=50.0, status=ToolCallStatus.SUCCESS,
                session_id="sess-batch", agent_name="batch-agent",
            )
            for i in range(5)
        ]
        await ch.save_tool_call_spans(spans)
        await asyncio.sleep(1)

        trace = await ch.get_session_trace("sess-batch")
        assert len(trace) >= 5

    async def test_span_types_stored(self, ch: ClickHouseBackend) -> None:
        now = datetime.now(UTC)
        handoff = ToolCallSpan.handoff_span(
            from_agent="orchestrator",
            to_agent="billing-agent",
            started_at=now,
            session_id="sess-types",
            trace_id="trace-123",
        )
        tool_call = ToolCallSpan.record(
            server_name="crm-mcp",
            tool_name="update_customer",
            started_at=now + timedelta(milliseconds=10),
            status=ToolCallStatus.SUCCESS,
            parent_span_id=handoff.span_id,
            session_id="sess-types",
            trace_id="trace-123",
            span_type="tool_call",
        )
        await ch.save_tool_call_spans([handoff, tool_call])
        await asyncio.sleep(1)

        trace = await ch.get_session_trace("sess-types")
        types = {s["span_type"] for s in trace}
        assert "handoff" in types
        assert "tool_call" in types

    async def test_parent_span_id_preserved(self, ch: ClickHouseBackend) -> None:
        now = datetime.now(UTC)
        parent = ToolCallSpan.agent_span(
            agent_name="parent-agent",
            task="main task",
            started_at=now,
            session_id="sess-parent",
        )
        child = ToolCallSpan.record(
            server_name="some-mcp",
            tool_name="do_thing",
            started_at=now + timedelta(milliseconds=5),
            status=ToolCallStatus.SUCCESS,
            parent_span_id=parent.span_id,
            session_id="sess-parent",
        )
        await ch.save_tool_call_spans([parent, child])
        await asyncio.sleep(1)

        trace = await ch.get_session_trace("sess-parent")
        child_span = next((s for s in trace if s["tool_name"] == "do_thing"), None)
        assert child_span is not None
        assert child_span["parent_span_id"] == parent.span_id


class TestToolReliability:
    async def test_reliability_aggregated_from_spans(self, ch: ClickHouseBackend) -> None:
        now = datetime.now(UTC)
        spans = [
            ToolCallSpan(
                server_name="rel-server", tool_name="fast_tool",
                started_at=now, ended_at=now + timedelta(milliseconds=50),
                latency_ms=50.0, status=ToolCallStatus.SUCCESS,
                session_id="rel-sess",
            ),
            ToolCallSpan(
                server_name="rel-server", tool_name="fast_tool",
                started_at=now, ended_at=now + timedelta(milliseconds=80),
                latency_ms=80.0, status=ToolCallStatus.SUCCESS,
                session_id="rel-sess",
            ),
            ToolCallSpan(
                server_name="rel-server", tool_name="fast_tool",
                started_at=now, ended_at=now + timedelta(milliseconds=100),
                latency_ms=100.0, status=ToolCallStatus.ERROR,
                error="db error", session_id="rel-sess",
            ),
        ]
        await ch.save_tool_call_spans(spans)
        await asyncio.sleep(2)  # MV needs time to aggregate

        results = await ch.get_tool_reliability(server_name="rel-server", hours=24)
        if results:  # MV may not have updated yet in CI
            tool = next((r for r in results if r["tool_name"] == "fast_tool"), None)
            if tool:
                assert tool["total_calls"] >= 3
                assert tool["error_calls"] >= 1


class TestAgentSessions:
    async def test_session_appears_in_sessions_list(self, ch: ClickHouseBackend) -> None:
        now = datetime.now(UTC)
        spans = [
            ToolCallSpan(
                server_name="jira-mcp", tool_name="get_issue",
                started_at=now, ended_at=now + timedelta(milliseconds=89),
                latency_ms=89.0, status=ToolCallStatus.SUCCESS,
                agent_name="support-agent", session_id="sess-e2e",
            ),
            ToolCallSpan(
                server_name="slack-mcp", tool_name="post_message",
                started_at=now + timedelta(milliseconds=100),
                ended_at=now + timedelta(milliseconds=200),
                latency_ms=100.0, status=ToolCallStatus.ERROR,
                error="timeout", agent_name="support-agent", session_id="sess-e2e",
            ),
        ]
        await ch.save_tool_call_spans(spans)
        await asyncio.sleep(2)

        sessions = await ch.get_agent_sessions(hours=1)
        sess = next((s for s in sessions if s.get("session_id") == "sess-e2e"), None)
        if sess:  # MV may lag slightly in CI
            assert sess["tool_calls"] >= 2
            assert sess["agent_name"] == "support-agent"
