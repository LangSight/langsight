from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from langsight.costs.engine import CostRule, aggregate_cost_rows
from langsight.sdk.models import ToolCallSpan, ToolCallStatus
from langsight.storage.clickhouse import ClickHouseBackend

TEST_DB = "langsight_costs_test"

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
async def ch():
    import clickhouse_connect

    admin = await clickhouse_connect.get_async_client(host="localhost", port=8123)
    await admin.command(f"DROP DATABASE IF EXISTS {TEST_DB}")
    await admin.command(f"CREATE DATABASE {TEST_DB}")
    await admin.close()

    backend = await ClickHouseBackend.open(host="localhost", port=8123, database=TEST_DB)
    yield backend
    await backend.close()

    admin2 = await clickhouse_connect.get_async_client(host="localhost", port=8123)
    await admin2.command(f"DROP DATABASE IF EXISTS {TEST_DB}")
    await admin2.close()


class TestCostBreakdown:
    async def test_aggregates_costs_from_traced_tool_calls(self, ch: ClickHouseBackend) -> None:
        now = datetime.now(UTC)
        spans = [
            ToolCallSpan(
                server_name="pg-main",
                tool_name="query",
                started_at=now,
                ended_at=now + timedelta(milliseconds=10),
                latency_ms=10.0,
                status=ToolCallStatus.SUCCESS,
                agent_name="support-agent",
                session_id="sess-1",
            ),
            ToolCallSpan(
                server_name="pg-main",
                tool_name="query",
                started_at=now + timedelta(milliseconds=20),
                ended_at=now + timedelta(milliseconds=30),
                latency_ms=10.0,
                status=ToolCallStatus.SUCCESS,
                agent_name="support-agent",
                session_id="sess-1",
            ),
            ToolCallSpan(
                server_name="s3-assets",
                tool_name="read_object",
                started_at=now + timedelta(milliseconds=40),
                ended_at=now + timedelta(milliseconds=70),
                latency_ms=30.0,
                status=ToolCallStatus.SUCCESS,
                agent_name="billing-agent",
                session_id="sess-2",
            ),
        ]

        await ch.save_tool_call_spans(spans)
        await asyncio.sleep(1)

        rows = await ch.get_cost_call_counts(hours=24)
        by_tool, by_agent, by_session = aggregate_cost_rows(
            rows,
            [
                CostRule(server="pg-*", tool="query", cost_per_call=0.005),
                CostRule(server="s3-*", tool="read_object", cost_per_call=0.002),
            ],
        )

        assert len(by_tool) == 2
        assert by_tool[0].server_name == "pg-main"
        assert by_tool[0].total_calls == 2
        assert by_tool[0].total_cost_usd == 0.01

        assert len(by_agent) == 2
        assert by_agent[0].agent_name == "support-agent"
        assert by_agent[0].total_calls == 2
        assert by_agent[0].total_cost_usd == 0.01

        assert len(by_session) == 2
        assert by_session[0].session_id == "sess-1"
        assert by_session[0].total_calls == 2
        assert by_session[0].total_cost_usd == 0.01
