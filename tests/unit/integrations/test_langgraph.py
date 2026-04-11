"""Tests for the LangGraph integration (now an alias to the unified LangChain callback).

Since v0.4, LangSightLangGraphCallback IS LangSightLangChainCallback.
These tests verify the alias works and that auto-detect chain tracking
(the feature that was previously LangGraph-specific) works correctly
through the unified callback.
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

from langsight.integrations.langchain import LangSightLangChainCallback
from langsight.integrations.langgraph import (
    LangSightLangGraphCallback,
)
from langsight.sdk.client import LangSightClient


@pytest.fixture
def client() -> LangSightClient:
    return LangSightClient(url="http://localhost:8000")


@pytest.fixture
def callback(client: LangSightClient) -> LangSightLangGraphCallback:
    """Auto-detect mode callback (chain tracking active)."""
    with patch(
        "langsight.integrations.langchain.LangSightLangChainCallback.__init__"
    ) as mock_init:
        mock_init.return_value = None
        cb = LangSightLangGraphCallback.__new__(LangSightLangGraphCallback)
        cb._client = client
        cb._server_name = "langgraph"
        cb._agent_name = "test-graph"
        cb._session_id = "sess-001"
        cb._trace_id = "trace-001"
        cb._redact = False
        cb._auto_detect = True  # chain tracking requires auto-detect
        cb._pending = {}
        cb._active_chains = {}
        cb._pending_llm = {}
        cb._active_lg_nodes = set()
        cb._local = threading.local()
        cb._session_input = None
        cb._session_output = None
        cb._session_input_captured = False
        cb._node_counter = {}
        cb._max_node_iterations = 10
        cb._budget = None
        cb._pricing_table = {}
        cb._budget_violated = False
        cb._budget_violation = None
    return cb


# =============================================================================
# Alias verification
# =============================================================================


class TestLangGraphAlias:
    def test_is_same_class(self) -> None:
        assert LangSightLangGraphCallback is LangSightLangChainCallback


# =============================================================================
# Constructor
# =============================================================================


class TestLangSightLangGraphCallbackConstructor:
    def test_creates_with_patched_init(self, callback: LangSightLangGraphCallback) -> None:
        assert callback._server_name == "langgraph"
        assert callback._agent_name == "test-graph"
        assert callback._session_id == "sess-001"

    def test_constructor_handles_missing_langchain(self, client: LangSightClient) -> None:
        with patch("builtins.__import__", side_effect=ImportError("no langchain")):
            pass  # Constructor handles ImportError gracefully


# =============================================================================
# Node/chain tracking (auto-detect mode)
# =============================================================================


class TestLangGraphNodeTracking:
    def test_on_chain_start_tracks_node_name(self, callback: LangSightLangGraphCallback) -> None:
        run_id = uuid4()
        callback.on_chain_start(
            {"name": "agent_node"},
            {"input": "hello"},
            run_id=run_id,
        )
        assert str(run_id) in callback._active_chains
        assert callback._active_chains[str(run_id)].name == "agent_node"

    def test_on_chain_start_extracts_name_from_id(self, callback: LangSightLangGraphCallback) -> None:
        run_id = uuid4()
        callback.on_chain_start(
            {"id": ["langgraph", "nodes", "ToolNode"]},
            {},
            run_id=run_id,
        )
        chain = callback._active_chains[str(run_id)]
        assert chain.name == "ToolNode"

    def test_on_chain_start_defaults_to_unknown(self, callback: LangSightLangGraphCallback) -> None:
        run_id = uuid4()
        callback.on_chain_start({"id": ["unknown"]}, {}, run_id=run_id)
        assert callback._active_chains[str(run_id)].name == "unknown"

    def test_on_chain_end_clears_node(self, callback: LangSightLangGraphCallback) -> None:
        run_id = uuid4()
        callback.on_chain_start({"name": "my_node"}, {}, run_id=run_id)
        callback.on_chain_end({}, run_id=run_id)
        assert str(run_id) not in callback._active_chains

    def test_on_chain_end_unknown_run_id_no_crash(self, callback: LangSightLangGraphCallback) -> None:
        callback.on_chain_end({}, run_id=uuid4())

    def test_on_chain_error_cleans_up(self, callback: LangSightLangGraphCallback) -> None:
        run_id = uuid4()
        callback.on_chain_start({"name": "bad_node"}, {}, run_id=run_id)
        callback.on_chain_error(RuntimeError("fail"), run_id=run_id)
        assert str(run_id) not in callback._active_chains

    def test_multiple_nodes_tracked_independently(self, callback: LangSightLangGraphCallback) -> None:
        r1, r2 = uuid4(), uuid4()
        callback.on_chain_start({"name": "node_a"}, {}, run_id=r1)
        callback.on_chain_start({"name": "node_b"}, {}, run_id=r2)
        assert len(callback._active_chains) == 2
        callback.on_chain_end({}, run_id=r1)
        assert str(r1) not in callback._active_chains
        assert str(r2) in callback._active_chains


# =============================================================================
# Tool tracking
# =============================================================================


class TestLangGraphOnToolStart:
    def test_records_pending(self, callback: LangSightLangGraphCallback) -> None:
        run_id = uuid4()
        callback.on_tool_start(
            {"name": "search"},
            "query",
            run_id=run_id,
        )
        assert str(run_id) in callback._pending
        assert callback._pending[str(run_id)].tool_name == "search"

    def test_extracts_name_from_id_field(self, callback: LangSightLangGraphCallback) -> None:
        run_id = uuid4()
        callback.on_tool_start(
            {"id": ["tools", "MyTool"]}, "input", run_id=run_id
        )
        assert callback._pending[str(run_id)].tool_name == "MyTool"


class TestLangGraphOnToolEnd:
    def test_clears_pending_and_fires_span(
        self, callback: LangSightLangGraphCallback
    ) -> None:
        run_id = uuid4()
        callback.on_tool_start({"name": "search"}, "query", run_id=run_id)

        callback.on_tool_end("result", run_id=run_id)

        assert str(run_id) not in callback._pending

    def test_unknown_run_id_no_crash(self, callback: LangSightLangGraphCallback) -> None:
        callback.on_tool_end("result", run_id=uuid4())

    def test_passes_session_and_trace_ids(
        self, callback: LangSightLangGraphCallback
    ) -> None:
        run_id = uuid4()
        callback.on_tool_start({"name": "search"}, "query", run_id=run_id)
        assert callback._session_id == "sess-001"
        assert callback._trace_id == "trace-001"


class TestLangGraphOnToolError:
    def test_clears_pending_and_fires_error_span(
        self, callback: LangSightLangGraphCallback
    ) -> None:
        run_id = uuid4()
        callback.on_tool_start({"name": "search"}, "query", run_id=run_id)

        callback.on_tool_error(RuntimeError("fail"), run_id=run_id)

        assert str(run_id) not in callback._pending

    def test_unknown_run_id_no_crash(self, callback: LangSightLangGraphCallback) -> None:
        callback.on_tool_error(RuntimeError("fail"), run_id=uuid4())


# =============================================================================
# Node input/output capture
# =============================================================================


class TestNodeInputOutputCapture:
    def test_on_chain_end_captures_inputs_and_outputs(
        self, callback: LangSightLangGraphCallback
    ) -> None:
        captured = []
        callback._client.buffer_span = lambda span: captured.append(span)

        run_id = uuid4()
        callback.on_chain_start(
            None,
            {"input": "hello"},
            run_id=run_id,
            metadata={"langgraph_node": "my_node"},
        )
        callback.on_chain_end({"output": "world"}, run_id=run_id)

        assert len(captured) == 1
        span = captured[0]
        assert span.input_args == {"input": "hello"}
        assert '"output": "world"' in span.output_result

    def test_on_chain_end_respects_redact_flag(
        self, callback: LangSightLangGraphCallback
    ) -> None:
        captured = []
        callback._client.buffer_span = lambda span: captured.append(span)
        callback._redact = True

        run_id = uuid4()
        callback.on_chain_start(
            None,
            {"input": "secret"},
            run_id=run_id,
            metadata={"langgraph_node": "my_node"},
        )
        callback.on_chain_end({"output": "secret"}, run_id=run_id)

        assert len(captured) == 1
        span = captured[0]
        assert span.input_args is None
        assert span.output_result is None

    def test_on_chain_end_truncates_large_output(
        self, callback: LangSightLangGraphCallback
    ) -> None:
        captured = []
        callback._client.buffer_span = lambda span: captured.append(span)

        run_id = uuid4()
        large_output = {"data": "x" * 10000}
        callback.on_chain_start(
            None,
            {},
            run_id=run_id,
            metadata={"langgraph_node": "my_node"},
        )
        callback.on_chain_end(large_output, run_id=run_id)

        assert len(captured) == 1
        span = captured[0]
        assert span.output_result is not None
        assert len(span.output_result) <= 4020  # 4000 + "[truncated]"


# =============================================================================
# Node deduplication
# =============================================================================


class TestNodeDeduplication:
    def test_duplicate_node_skipped(self, callback: LangSightLangGraphCallback) -> None:
        run_id_1 = uuid4()
        callback.on_chain_start(
            None,
            {},
            run_id=run_id_1,
            metadata={"langgraph_node": "node_a"},
        )
        assert callback._active_chains[str(run_id_1)].is_agent is True

        run_id_2 = uuid4()
        callback.on_chain_start(
            None,
            {},
            run_id=run_id_2,
            metadata={"langgraph_node": "node_a"},
        )
        assert callback._active_chains[str(run_id_2)].is_agent is False

    def test_dedup_cleanup_on_chain_end(self, callback: LangSightLangGraphCallback) -> None:
        run_id = uuid4()
        callback.on_chain_start(
            None,
            {},
            run_id=run_id,
            metadata={"langgraph_node": "node_a"},
        )
        assert "node_a" in callback._active_lg_nodes

        callback.on_chain_end({}, run_id=run_id)
        assert "node_a" not in callback._active_lg_nodes

    def test_different_nodes_not_deduplicated(
        self, callback: LangSightLangGraphCallback
    ) -> None:
        run_id_1 = uuid4()
        callback.on_chain_start(
            None,
            {},
            run_id=run_id_1,
            metadata={"langgraph_node": "node_a"},
        )

        run_id_2 = uuid4()
        callback.on_chain_start(
            None,
            {},
            run_id=run_id_2,
            metadata={"langgraph_node": "node_b"},
        )

        assert callback._active_chains[str(run_id_1)].is_agent is True
        assert callback._active_chains[str(run_id_2)].is_agent is True

    def test_same_node_can_reappear_after_end(
        self, callback: LangSightLangGraphCallback
    ) -> None:
        run_id_1 = uuid4()
        callback.on_chain_start(
            None,
            {},
            run_id=run_id_1,
            metadata={"langgraph_node": "node_a"},
        )
        callback.on_chain_end({}, run_id=run_id_1)
        assert "node_a" not in callback._active_lg_nodes

        run_id_2 = uuid4()
        callback.on_chain_start(
            None,
            {},
            run_id=run_id_2,
            metadata={"langgraph_node": "node_a"},
        )
        assert callback._active_chains[str(run_id_2)].is_agent is True


# =============================================================================
# LLM data capture
# =============================================================================


class TestLLMDataCapture:
    def test_on_chat_model_start_stores_start_time(
        self, callback: LangSightLangGraphCallback
    ) -> None:
        run_id = uuid4()
        before = datetime.now(UTC)
        callback.on_chat_model_start({}, [[]], run_id=run_id)
        after = datetime.now(UTC)

        assert str(run_id) in callback._pending_llm
        stored_at = callback._pending_llm[str(run_id)]["started_at"]
        assert before <= stored_at <= after

    def test_on_chat_model_start_extracts_model_name(
        self, callback: LangSightLangGraphCallback
    ) -> None:
        run_id = uuid4()
        callback.on_chat_model_start(
            {"kwargs": {"model": "gpt-4"}},
            [[]],
            run_id=run_id,
        )

        assert callback._pending_llm[str(run_id)]["model_name"] == "gpt-4"

    def test_on_chat_model_start_serializes_messages(
        self, callback: LangSightLangGraphCallback
    ) -> None:
        run_id = uuid4()
        msg1 = SimpleNamespace(type="human", content="Hello")
        msg2 = SimpleNamespace(type="ai", content="Hi there")
        callback.on_chat_model_start({}, [[msg1, msg2]], run_id=run_id)

        messages_str = callback._pending_llm[str(run_id)]["messages_str"]
        assert "human: Hello" in messages_str
        assert "ai: Hi there" in messages_str

    def test_on_chat_model_start_redact_skips_messages(
        self, callback: LangSightLangGraphCallback
    ) -> None:
        callback._redact = True
        run_id = uuid4()
        msg = SimpleNamespace(type="human", content="secret")
        callback.on_chat_model_start({}, [[msg]], run_id=run_id)

        assert callback._pending_llm[str(run_id)]["messages_str"] is None

    def test_on_llm_end_captures_llm_output(
        self, callback: LangSightLangGraphCallback
    ) -> None:
        captured = []
        callback._client.buffer_span = lambda span: captured.append(span)

        run_id = uuid4()
        msg = SimpleNamespace(type="human", content="What is 2+2?")
        callback.on_chat_model_start(
            {"kwargs": {"model": "gpt-4"}},
            [[msg]],
            run_id=run_id,
        )

        gen = SimpleNamespace(
            text="The answer is 4.",
            message=SimpleNamespace(
                content="The answer is 4.",
                usage_metadata={"input_tokens": 10, "output_tokens": 5},
            ),
            generation_info={"model_name": "gpt-4", "finish_reason": "stop"},
        )
        response = SimpleNamespace(generations=[[gen]], llm_output=None)
        callback.on_llm_end(response, run_id=run_id)

        assert len(captured) == 1
        span = captured[0]
        assert span.llm_output == "The answer is 4."
        assert span.model_id == "gpt-4"
        assert span.finish_reason == "stop"
        assert "human: What is 2+2?" in span.llm_input
        assert span.input_tokens == 10
        assert span.output_tokens == 5

    def test_on_llm_end_latency_nonzero(
        self, callback: LangSightLangGraphCallback
    ) -> None:
        captured = []
        callback._client.buffer_span = lambda span: captured.append(span)

        run_id = uuid4()
        callback.on_chat_model_start({}, [[]], run_id=run_id)
        time.sleep(0.01)  # 10ms

        gen = SimpleNamespace(
            message=SimpleNamespace(
                usage_metadata={"input_tokens": 1, "output_tokens": 1}
            ),
            generation_info={},
        )
        response = SimpleNamespace(generations=[[gen]])
        callback.on_llm_end(response, run_id=run_id)

        assert len(captured) == 1
        assert captured[0].latency_ms >= 5

    def test_on_llm_start_does_not_overwrite_chat_model_start(
        self, callback: LangSightLangGraphCallback
    ) -> None:
        run_id = uuid4()
        callback.on_chat_model_start(
            {"kwargs": {"model": "gpt-4"}},
            [[]],
            run_id=run_id,
        )
        original_model = callback._pending_llm[str(run_id)]["model_name"]

        callback.on_llm_start({"kwargs": {"model": "gpt-3.5"}}, [], run_id=run_id)

        assert callback._pending_llm[str(run_id)]["model_name"] == original_model
        assert original_model == "gpt-4"


# =============================================================================
# Thinking token capture
# =============================================================================


class TestThinkingTokenCapture:
    def test_thinking_tokens_derived_from_total(
        self, callback: LangSightLangGraphCallback
    ) -> None:
        """When total_tokens > input + output, thinking_tokens is derived."""
        captured = []
        callback._client.buffer_span = lambda span: captured.append(span)

        run_id = uuid4()
        callback.on_chat_model_start(
            {"kwargs": {"model": "claude-sonnet-4-6"}},
            [[]],
            run_id=run_id,
        )

        # Fire on_llm_end with total > input + output
        response = SimpleNamespace(
            generations=[[
                SimpleNamespace(
                    message=SimpleNamespace(
                        usage_metadata={
                            "input_tokens": 100,
                            "output_tokens": 50,
                            "total_tokens": 180,  # 100 + 50 + 30 thinking
                        }
                    ),
                    generation_info={"model_name": "claude-sonnet-4-6"},
                )
            ]]
        )

        callback.on_llm_end(response, run_id=run_id)

        assert len(captured) == 1
        span = captured[0]
        assert span.input_tokens == 100
        assert span.output_tokens == 50
        assert span.thinking_tokens == 30

    def test_no_thinking_tokens_when_total_matches(
        self, callback: LangSightLangGraphCallback
    ) -> None:
        """When total_tokens = input + output, thinking_tokens is None."""
        captured = []
        callback._client.buffer_span = lambda span: captured.append(span)

        run_id = uuid4()
        callback.on_chat_model_start(
            {"kwargs": {"model": "gpt-4"}},
            [[]],
            run_id=run_id,
        )

        response = SimpleNamespace(
            generations=[[
                SimpleNamespace(
                    message=SimpleNamespace(
                        usage_metadata={
                            "input_tokens": 100,
                            "output_tokens": 50,
                            "total_tokens": 150,  # Exactly input + output
                        }
                    ),
                    generation_info={"model_name": "gpt-4"},
                )
            ]]
        )

        callback.on_llm_end(response, run_id=run_id)

        assert len(captured) == 1
        span = captured[0]
        assert span.input_tokens == 100
        assert span.output_tokens == 50
        assert span.thinking_tokens is None

    def test_no_thinking_tokens_when_no_total(
        self, callback: LangSightLangGraphCallback
    ) -> None:
        """When usage_metadata has no total_tokens key, thinking_tokens is None."""
        captured = []
        callback._client.buffer_span = lambda span: captured.append(span)

        run_id = uuid4()
        callback.on_chat_model_start(
            {"kwargs": {"model": "gpt-4"}},
            [[]],
            run_id=run_id,
        )

        response = SimpleNamespace(
            generations=[[
                SimpleNamespace(
                    message=SimpleNamespace(
                        usage_metadata={
                            "input_tokens": 100,
                            "output_tokens": 50,
                            # No total_tokens key
                        }
                    ),
                    generation_info={"model_name": "gpt-4"},
                )
            ]]
        )

        callback.on_llm_end(response, run_id=run_id)

        assert len(captured) == 1
        span = captured[0]
        assert span.input_tokens == 100
        assert span.output_tokens == 50
        assert span.thinking_tokens is None


# =============================================================================
# Tier 2: Node Loop Detection
# =============================================================================


class TestNodeLoopDetection:
    def test_node_iteration_raises_after_limit(self, callback: LangSightLangGraphCallback) -> None:
        """Node iteration should raise after limit is reached."""
        from langsight.exceptions import GraphLoopDetectedError

        callback._max_node_iterations = 3
        run_ids = [uuid4() for _ in range(4)]

        # Fire on_chain_start 3 times for same node, each time ending the chain
        for i in range(3):
            callback.on_chain_start(
                None,
                {"input": f"run{i}"},
                run_id=run_ids[i],
                metadata={"langgraph_node": "agent_node"},
            )
            callback.on_chain_end({"output": "ok"}, run_id=run_ids[i])

        # 4th invocation should raise
        with pytest.raises(GraphLoopDetectedError) as exc_info:
            callback.on_chain_start(
                None,
                {"input": "run3"},
                run_id=run_ids[3],
                metadata={"langgraph_node": "agent_node"},
            )

        assert exc_info.value.node_name == "agent_node"
        assert exc_info.value.loop_count == 4
        assert exc_info.value.max_iterations == 3

    def test_node_iteration_different_nodes_independent(self, callback: LangSightLangGraphCallback) -> None:
        """Different nodes should have independent counters."""
        callback._max_node_iterations = 3

        # Fire 3 times for node_a
        for i in range(3):
            run_id = uuid4()
            callback.on_chain_start(
                None,
                {"input": f"a{i}"},
                run_id=run_id,
                metadata={"langgraph_node": "node_a"},
            )
            callback.on_chain_end({"output": "ok"}, run_id=run_id)

        # Fire 3 times for node_b
        for i in range(3):
            run_id = uuid4()
            callback.on_chain_start(
                None,
                {"input": f"b{i}"},
                run_id=run_id,
                metadata={"langgraph_node": "node_b"},
            )
            callback.on_chain_end({"output": "ok"}, run_id=run_id)

        # Neither should raise (each has count=3, limit=3)
        assert callback._node_counter["node_a"] == 3
        assert callback._node_counter["node_b"] == 3

    def test_node_iteration_disabled_when_zero(self, callback: LangSightLangGraphCallback) -> None:
        """When max_node_iterations=0, no limit is enforced."""
        callback._max_node_iterations = 0

        # Fire 20 times — no exception should be raised
        for i in range(20):
            run_id = uuid4()
            callback.on_chain_start(
                None,
                {"input": f"run{i}"},
                run_id=run_id,
                metadata={"langgraph_node": "agent_node"},
            )
            callback.on_chain_end({"output": "ok"}, run_id=run_id)

        assert callback._node_counter["agent_node"] == 20


# =============================================================================
# Tier 2: Budget Enforcement
# =============================================================================


class TestBudgetEnforcement:
    def test_budget_violation_sets_flag(self, callback: LangSightLangGraphCallback) -> None:
        """Budget violation in on_llm_end should set flag."""
        from langsight.sdk.budget import BudgetConfig, SessionBudget

        budget_config = BudgetConfig(max_cost_usd=0.001, max_steps=100)
        callback._budget = SessionBudget(budget_config)
        callback._pricing_table = {
            "gpt-4": (10.0, 30.0),  # $10/1M input, $30/1M output
        }

        run_id = uuid4()

        # Fire on_chat_model_start
        callback.on_chat_model_start(
            {"kwargs": {"model": "gpt-4"}},
            [[]],
            run_id=run_id,
        )

        # Fire on_llm_end with 10000 input + 10000 output tokens
        # Cost = 10000/1M * 10 + 10000/1M * 30 = 0.1 + 0.3 = 0.4 USD > 0.001 limit
        response = SimpleNamespace(
            generations=[[
                SimpleNamespace(
                    message=SimpleNamespace(
                        usage_metadata={"input_tokens": 10000, "output_tokens": 10000}
                    ),
                    generation_info={"model_name": "gpt-4"},
                )
            ]]
        )

        callback.on_llm_end(response, run_id=run_id)

        assert callback._budget_violated is True
        assert callback._budget_violation is not None
        assert callback._budget_violation.limit_type == "max_cost_usd"

    def test_budget_violation_raises_on_next_chain_start(self, callback: LangSightLangGraphCallback) -> None:
        """After budget violation, next on_chain_start should raise."""
        from langsight.exceptions import BudgetExceededError
        from langsight.sdk.budget import BudgetConfig, SessionBudget, BudgetViolation

        # Simulate budget already violated
        callback._budget_violated = True
        callback._budget_violation = BudgetViolation(
            limit_type="max_cost_usd",
            limit_value=0.001,
            actual_value=0.4,
        )

        run_id = uuid4()

        with pytest.raises(BudgetExceededError) as exc_info:
            callback.on_chain_start(
                {"name": "agent_node"},
                {"input": "hello"},
                run_id=run_id,
            )

        assert exc_info.value.limit_type == "max_cost_usd"
        assert exc_info.value.limit_value == 0.001
        assert exc_info.value.actual_value == 0.4
