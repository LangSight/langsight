from __future__ import annotations

from langsight.costs.engine import CostRule, aggregate_cost_rows, find_cost_per_call


class TestFindCostPerCall:
    def test_returns_first_matching_rule(self) -> None:
        rules = [
            CostRule(server="pg-*", tool="query", cost_per_call=0.005),
            CostRule(server="*", tool="*", cost_per_call=0.001),
        ]

        assert find_cost_per_call(rules, "pg-main", "query") == 0.005

    def test_falls_back_to_default_when_no_rule_matches(self) -> None:
        rules = [CostRule(server="billing-*", tool="send_invoice", cost_per_call=0.02)]

        assert find_cost_per_call(rules, "pg-main", "query") == 0.001


class TestAggregateCostRows:
    def test_aggregates_tool_agent_and_session_totals(self) -> None:
        rules = [
            CostRule(server="pg-*", tool="query", cost_per_call=0.005),
            CostRule(server="s3-*", tool="read_object", cost_per_call=0.002),
            CostRule(server="*", tool="*", cost_per_call=0.001),
        ]
        rows = [
            {
                "server_name": "pg-main",
                "tool_name": "query",
                "agent_name": "support-agent",
                "session_id": "sess-1",
                "total_calls": 10,
            },
            {
                "server_name": "s3-assets",
                "tool_name": "read_object",
                "agent_name": "support-agent",
                "session_id": "sess-1",
                "total_calls": 4,
            },
            {
                "server_name": "pg-main",
                "tool_name": "query",
                "agent_name": "billing-agent",
                "session_id": "sess-2",
                "total_calls": 6,
            },
        ]

        by_tool, by_agent, by_session = aggregate_cost_rows(rows, rules)

        assert len(by_tool) == 2
        assert by_tool[0].server_name == "pg-main"
        assert by_tool[0].tool_name == "query"
        assert by_tool[0].total_calls == 16
        assert by_tool[0].total_cost_usd == 0.08

        assert len(by_agent) == 2
        assert by_agent[0].agent_name == "support-agent"
        assert by_agent[0].total_calls == 14
        assert by_agent[0].total_cost_usd == 0.058

        assert len(by_session) == 2
        assert by_session[0].session_id == "sess-1"
        assert by_session[0].total_calls == 14
        assert by_session[0].total_cost_usd == 0.058

    def test_skips_session_rollup_when_session_id_missing(self) -> None:
        rows = [
            {
                "server_name": "pg-main",
                "tool_name": "query",
                "agent_name": None,
                "session_id": None,
                "total_calls": 3,
            }
        ]

        by_tool, by_agent, by_session = aggregate_cost_rows(rows, [CostRule()])

        assert len(by_tool) == 1
        assert len(by_agent) == 1
        assert by_agent[0].agent_name == "unknown"
        assert by_session == []
