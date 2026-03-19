"""Unit tests for Phase 7 model-based cost tracking.

Covers:
  - ModelPricingLookup: cost_for, has_model, duplicate-model-id precedence
  - aggregate_cost_rows: token-based vs call-based routing, token accumulation,
    mixed-type totals
  - ModelPricing (models.py): is_active property, cost_for method
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from langsight.costs.engine import CostRule, ModelPricingLookup, aggregate_cost_rows
from langsight.models import ModelPricing

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SONNET_INPUT_PER_1M = 3.0
SONNET_OUTPUT_PER_1M = 15.0
SONNET_MODEL_ID = "claude-sonnet-4-6"


def _sonnet_pricing_row() -> ModelPricing:
    """Return a ModelPricing instance for claude-sonnet-4-6."""
    return ModelPricing(
        id="mp-sonnet-46",
        provider="anthropic",
        model_id=SONNET_MODEL_ID,
        display_name="Claude Sonnet 4.6",
        input_per_1m_usd=SONNET_INPUT_PER_1M,
        output_per_1m_usd=SONNET_OUTPUT_PER_1M,
    )


def _default_rules() -> list[CostRule]:
    return [CostRule(server="*", tool="*", cost_per_call=0.001)]


# ---------------------------------------------------------------------------
# TestModelPricingLookup
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestModelPricingLookup:
    def test_cost_for_known_model(self) -> None:
        """1000 input + 200 output on sonnet ($3/M in, $15/M out) = 0.003 + 0.003 = 0.006."""
        lookup = ModelPricingLookup([_sonnet_pricing_row()])
        cost = lookup.cost_for(SONNET_MODEL_ID, input_tokens=1000, output_tokens=200)
        assert cost == pytest.approx(0.006)

    def test_cost_for_unknown_model_returns_zero(self) -> None:
        """Unknown model_id must return 0.0, not raise."""
        lookup = ModelPricingLookup([_sonnet_pricing_row()])
        cost = lookup.cost_for("gpt-99-turbo", input_tokens=50_000, output_tokens=10_000)
        assert cost == 0.0

    def test_has_model_true_for_known(self) -> None:
        lookup = ModelPricingLookup([_sonnet_pricing_row()])
        assert lookup.has_model(SONNET_MODEL_ID) is True

    def test_has_model_false_for_unknown(self) -> None:
        lookup = ModelPricingLookup([_sonnet_pricing_row()])
        assert lookup.has_model("not-a-real-model") is False

    def test_uses_first_entry_for_duplicate_model_ids(self) -> None:
        """When two rows share a model_id, the first row's pricing must win."""
        first = ModelPricing(
            id="mp-first",
            provider="anthropic",
            model_id=SONNET_MODEL_ID,
            display_name="Sonnet (first)",
            input_per_1m_usd=3.0,
            output_per_1m_usd=15.0,
        )
        second = ModelPricing(
            id="mp-second",
            provider="anthropic",
            model_id=SONNET_MODEL_ID,
            display_name="Sonnet (second — higher price)",
            input_per_1m_usd=99.0,
            output_per_1m_usd=99.0,
        )
        lookup = ModelPricingLookup([first, second])
        # Must use first row's pricing, not the second
        cost = lookup.cost_for(SONNET_MODEL_ID, input_tokens=1_000_000, output_tokens=1_000_000)
        assert cost == pytest.approx(18.0)  # 3 + 15 from first row


# ---------------------------------------------------------------------------
# TestAggregateWithTokenPricing
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAggregateWithTokenPricing:
    def test_token_based_when_model_and_tokens_present(self) -> None:
        """Row with model_id + token counts must produce a token_based CostEntry."""
        rows = [
            {
                "server_name": "llm-server",
                "tool_name": "complete",
                "agent_name": "my-agent",
                "session_id": "sess-1",
                "total_calls": 1,
                "model_id": SONNET_MODEL_ID,
                "input_tokens": 1000,
                "output_tokens": 200,
            }
        ]
        pricing = ModelPricingLookup([_sonnet_pricing_row()])
        by_tool, _, _ = aggregate_cost_rows(rows, _default_rules(), model_pricing=pricing)

        assert len(by_tool) == 1
        entry = by_tool[0]
        assert entry.cost_type == "token_based"
        assert entry.model_id == SONNET_MODEL_ID
        assert entry.total_cost_usd == pytest.approx(0.006)

    def test_call_based_when_no_model_id(self) -> None:
        """Row without model_id must fall back to call-based pricing from CostRule."""
        rows = [
            {
                "server_name": "pg-mcp",
                "tool_name": "query",
                "agent_name": "my-agent",
                "session_id": "sess-1",
                "total_calls": 5,
                # no model_id, no token counts
            }
        ]
        rules = [CostRule(server="pg-mcp", tool="query", cost_per_call=0.005)]
        pricing = ModelPricingLookup([_sonnet_pricing_row()])
        by_tool, _, _ = aggregate_cost_rows(rows, rules, model_pricing=pricing)

        entry = by_tool[0]
        assert entry.cost_type == "call_based"
        assert entry.model_id is None
        assert entry.total_cost_usd == pytest.approx(0.025)  # 5 * 0.005

    def test_call_based_when_no_tokens(self) -> None:
        """Row with model_id but missing token counts must fall back to call-based."""
        rows = [
            {
                "server_name": "llm-server",
                "tool_name": "complete",
                "agent_name": "my-agent",
                "session_id": "sess-1",
                "total_calls": 3,
                "model_id": SONNET_MODEL_ID,
                # input_tokens and output_tokens intentionally absent
            }
        ]
        pricing = ModelPricingLookup([_sonnet_pricing_row()])
        by_tool, _, _ = aggregate_cost_rows(rows, _default_rules(), model_pricing=pricing)

        entry = by_tool[0]
        assert entry.cost_type == "call_based"
        assert entry.total_cost_usd == pytest.approx(0.003)  # 3 * 0.001 default

    def test_call_based_when_model_not_in_pricing(self) -> None:
        """model_id present in row but absent from ModelPricingLookup → call_based."""
        rows = [
            {
                "server_name": "llm-server",
                "tool_name": "complete",
                "agent_name": "my-agent",
                "session_id": "sess-1",
                "total_calls": 2,
                "model_id": "some-unknown-model",
                "input_tokens": 500,
                "output_tokens": 100,
            }
        ]
        pricing = ModelPricingLookup([_sonnet_pricing_row()])  # only knows sonnet
        by_tool, _, _ = aggregate_cost_rows(rows, _default_rules(), model_pricing=pricing)

        entry = by_tool[0]
        assert entry.cost_type == "call_based"
        assert entry.model_id is None

    def test_token_counts_aggregated_across_rows(self) -> None:
        """Two rows for the same tool with 500 input each → total_input_tokens = 1000."""
        rows = [
            {
                "server_name": "llm-server",
                "tool_name": "complete",
                "agent_name": "agent-a",
                "session_id": "sess-1",
                "total_calls": 1,
                "model_id": SONNET_MODEL_ID,
                "input_tokens": 500,
                "output_tokens": 100,
            },
            {
                "server_name": "llm-server",
                "tool_name": "complete",
                "agent_name": "agent-b",
                "session_id": "sess-2",
                "total_calls": 1,
                "model_id": SONNET_MODEL_ID,
                "input_tokens": 500,
                "output_tokens": 100,
            },
        ]
        pricing = ModelPricingLookup([_sonnet_pricing_row()])
        by_tool, _, _ = aggregate_cost_rows(rows, _default_rules(), model_pricing=pricing)

        assert len(by_tool) == 1
        entry = by_tool[0]
        assert entry.total_input_tokens == 1000   # 500*1 + 500*1
        assert entry.total_output_tokens == 200   # 100*1 + 100*1

    def test_total_cost_splits_correctly_between_token_and_call_based(self) -> None:
        """Mix of token-based and call-based rows each appear in by_tool with correct types."""
        rows = [
            # token-based: 1000 input + 200 output on sonnet → $0.006
            {
                "server_name": "llm-server",
                "tool_name": "complete",
                "agent_name": "my-agent",
                "session_id": "sess-1",
                "total_calls": 1,
                "model_id": SONNET_MODEL_ID,
                "input_tokens": 1000,
                "output_tokens": 200,
            },
            # call-based: 4 calls × $0.005 → $0.020
            {
                "server_name": "pg-mcp",
                "tool_name": "query",
                "agent_name": "my-agent",
                "session_id": "sess-1",
                "total_calls": 4,
            },
        ]
        rules = [CostRule(server="pg-mcp", tool="query", cost_per_call=0.005)]
        pricing = ModelPricingLookup([_sonnet_pricing_row()])
        by_tool, _, _ = aggregate_cost_rows(rows, rules, model_pricing=pricing)

        by_type = {e.tool_name: e for e in by_tool}
        assert by_type["complete"].cost_type == "token_based"
        assert by_type["complete"].total_cost_usd == pytest.approx(0.006)
        assert by_type["query"].cost_type == "call_based"
        assert by_type["query"].total_cost_usd == pytest.approx(0.020)


# ---------------------------------------------------------------------------
# TestModelPricing (models.py)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestModelPricing:
    def test_is_active_when_effective_to_is_none(self) -> None:
        pricing = ModelPricing(
            id="mp-1",
            provider="anthropic",
            model_id=SONNET_MODEL_ID,
            display_name="Sonnet",
            input_per_1m_usd=3.0,
            output_per_1m_usd=15.0,
            effective_to=None,
        )
        assert pricing.is_active is True

    def test_is_inactive_when_effective_to_set(self) -> None:
        pricing = ModelPricing(
            id="mp-2",
            provider="anthropic",
            model_id=SONNET_MODEL_ID,
            display_name="Sonnet (old)",
            input_per_1m_usd=3.0,
            output_per_1m_usd=15.0,
            effective_to=datetime(2025, 1, 1, tzinfo=UTC),
        )
        assert pricing.is_active is False

    def test_cost_for_computes_correctly(self) -> None:
        """Same arithmetic as TestModelPricingLookup.test_cost_for_known_model.

        1000 input tokens at $3/M + 200 output tokens at $15/M = $0.003 + $0.003 = $0.006
        """
        pricing = ModelPricing(
            id="mp-3",
            provider="anthropic",
            model_id=SONNET_MODEL_ID,
            display_name="Sonnet",
            input_per_1m_usd=SONNET_INPUT_PER_1M,
            output_per_1m_usd=SONNET_OUTPUT_PER_1M,
        )
        cost = pricing.cost_for(input_tokens=1000, output_tokens=200)
        assert cost == pytest.approx(0.006)
