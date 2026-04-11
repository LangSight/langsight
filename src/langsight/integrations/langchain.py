"""
Unified LangChain + LangGraph integration for LangSight.

Auto-captures the full agent tree with ONE callback:

    from langsight.sdk import LangSightClient
    from langsight.integrations.langchain import LangSightLangChainCallback

    client = LangSightClient(url="http://localhost:8000", project_id="...")
    cb = LangSightLangChainCallback(client=client, session_id=sid, trace_id=tid)

    # Pass to ANY agent — auto-detects agents, tools, parent links
    result = await supervisor.ainvoke(input, config={"callbacks": [cb]})

Auto-detect mode (server_name omitted):
    - Agent names detected from LangGraph graph names via on_chain_start
    - Parent-child tree built via parent_run_id + cross-ainvoke tool stack
    - Prompt captured from first human message via on_chat_model_start

Fixed mode (server_name provided):
    - Backward-compatible with v0.3 behavior
    - server_name and agent_name fixed per instance

Works with LangChain, LangGraph, Langflow, and any LangChain-based framework.
Does NOT import langchain at module level — LangSight can be installed without it.
"""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog

from langsight.integrations.base import BaseIntegration
from langsight.sdk.client import LangSightClient
from langsight.sdk.models import SpanType, ToolCallSpan, ToolCallStatus

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Agent detection — skip framework-internal chain names
# ---------------------------------------------------------------------------

_SKIP_CHAIN_NAMES = frozenset(
    {
        # LangChain runnables
        "RunnableSequence",
        "RunnableLambda",
        "RunnableParallel",
        "RunnablePassthrough",
        "RunnableBranch",
        "RunnableAssign",
        "RunnableEach",
        "RunnableWithFallbacks",
        # LangGraph internals
        "ChannelWrite",
        "ChannelRead",
        "PregelNode",
        "PregelLoop",
        # Prompt / output parsers
        "ChatPromptTemplate",
        "PromptTemplate",
        "MessagesPlaceholder",
        "StrOutputParser",
        "JsonOutputParser",
        "PydanticOutputParser",
        # LLM wrappers
        "ChatOpenAI",
        "ChatAnthropic",
        "ChatGoogleGenerativeAI",
        "ChatVertexAI",
        "ChatOllama",
    }
)

# LangGraph internal node names (not user-defined agents)
_SKIP_NODE_NAMES = frozenset(
    {
        "tools",
        "tool_node",
        "__start__",
        "__end__",
        "agent",  # internal react-agent node, not the graph itself
    }
)

_MAX_FIELD_LEN = 4000


def _truncate(text: str, max_len: int = _MAX_FIELD_LEN) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "...[truncated]"


def _safe_json(obj: Any, max_len: int = _MAX_FIELD_LEN) -> str:
    try:
        text = json.dumps(obj, default=str, ensure_ascii=False)
    except (TypeError, ValueError, OverflowError):
        text = str(obj)
    return _truncate(text, max_len)


def _serialize_messages(messages: list[list[Any]], max_len: int = _MAX_FIELD_LEN) -> str:
    parts: list[str] = []
    try:
        for msg_list in messages:
            for msg in msg_list:
                role = getattr(msg, "type", "unknown")
                content = getattr(msg, "content", "")
                if isinstance(content, list):
                    content = json.dumps(content, default=str, ensure_ascii=False)
                parts.append(f"{role}: {content}")
    except (TypeError, AttributeError, IndexError):
        return _truncate(str(messages), max_len)
    return _truncate("\n".join(parts), max_len)


def _detect_agent_name(
    serialized: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> str | None:
    """Return agent name if this chain_start is a named agent, else None.

    Heuristic: a chain is an agent if it has a user-defined name that is
    not a framework-internal class or LangGraph internal node.
    """
    # LangGraph 0.0.x fires on_chain_start with serialized=None for nodes;
    # the actual node name is in metadata["langgraph_node"].
    node_from_meta = (metadata or {}).get("langgraph_node")
    if not serialized:
        if node_from_meta and node_from_meta not in _SKIP_NODE_NAMES:
            return str(node_from_meta)
        return None

    name = serialized.get("name", "")
    if not name or name in _SKIP_CHAIN_NAMES:
        # Fall back to metadata node name if serialized name is missing/internal
        if node_from_meta and node_from_meta not in _SKIP_NODE_NAMES:
            return str(node_from_meta)
        return None

    # LangGraph internal nodes appear in metadata
    if node_from_meta and node_from_meta in _SKIP_NODE_NAMES:
        return None

    return str(name)


# ---------------------------------------------------------------------------
# Internal state dataclasses
# ---------------------------------------------------------------------------


@dataclass
class _PendingTool:
    """State for a tool call that has started but not yet ended."""

    tool_name: str
    started_at: datetime
    input_str: str
    span_id: str  # pre-generated so sub-agents can reference it as parent
    agent_name: str | None = None  # enclosing agent (auto-detected)
    parent_span_id: str | None = None  # enclosing agent's span_id


@dataclass
class _ActiveChain:
    """State for an active chain (potential agent)."""

    name: str
    started_at: datetime
    is_agent: bool
    agent_span_id: str | None = None  # span_id of the agent span we emitted
    parent_span_id: str | None = None  # parent agent's span_id
    is_langgraph_node: bool = False  # True when name came from metadata["langgraph_node"]
    input_data: dict[str, Any] | None = None


@dataclass
class _ToolExecContext:
    """Entry in the thread-local tool execution stack for cross-ainvoke linking."""

    run_id: str
    span_id: str
    tool_name: str


# Module-level thread-local tool stack — shared across all callback instances
# so cross-ainvoke parent linking works when each sub-agent gets its own
# callback (the common LangGraph pattern where on_chain_start doesn't fire).
_global_tool_stack_local = threading.local()


def _get_global_tool_stack() -> list[_ToolExecContext]:
    """Return the thread-local tool execution stack."""
    if not hasattr(_global_tool_stack_local, "stack"):
        _global_tool_stack_local.stack = []
    from typing import cast as _cast

    return _cast(list[_ToolExecContext], _global_tool_stack_local.stack)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _try_flush(client: Any) -> None:
    """Best-effort trigger a flush if a running event loop is available.

    Called after buffering spans to speed up delivery. If no loop is available
    (between sub-agent ainvoke calls), the periodic flush loop or atexit handler
    will deliver the spans — nothing is lost.
    """
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running() and not loop.is_closed():
            loop.create_task(client.flush())
    except (RuntimeError, Exception):  # noqa: BLE001
        pass  # Flush loop or atexit will handle it


# ---------------------------------------------------------------------------
# Unified callback
# ---------------------------------------------------------------------------


class LangSightLangChainCallback(BaseIntegration):
    """Unified LangChain + LangGraph callback that auto-captures the agent tree.

    Two modes:
    - **Auto-detect** (server_name omitted): agents, servers, and parent links
      are detected automatically from LangGraph/LangChain metadata.
    - **Fixed** (server_name provided): backward-compatible v0.3 behavior where
      server_name and agent_name are fixed per callback instance.

    Works with LangChain agents, LangGraph workflows, Langflow, and any
    LangChain-based framework.
    """

    def __init__(
        self,
        client: LangSightClient,
        server_name: str | None = None,
        agent_name: str | None = None,
        session_id: str | None = None,
        trace_id: str | None = None,
        max_node_iterations: int = 10,
        budget: Any = None,  # SessionBudget | None
        pricing_table: dict[str, tuple[float, float]] | None = None,
    ) -> None:
        """Initialise the callback.

        Args:
            client: LangSightClient instance for sending spans.
            server_name: Fixed server name (legacy mode). When ``None``, auto-detect
                mode is enabled and server/agent names are inferred from callbacks.
            agent_name: Fixed agent name. Auto-detected when ``None``.
            session_id: Session grouping key. Auto-generated when ``None``.
            trace_id: Trace grouping key. Auto-generated when ``None``.
        """
        # Lazy import — try langchain-core first, fall back to langchain
        try:
            try:
                from langchain_core.callbacks.base import BaseCallbackHandler
            except ImportError:
                from langchain.callbacks.base import BaseCallbackHandler

            self.__class__.__bases__ = (BaseIntegration, BaseCallbackHandler)
            BaseCallbackHandler.__init__(self)
        except ImportError:
            logger.warning("langchain-core not installed. Install with: pip install langchain-core")

        # Auto-detect mode when server_name is not provided
        self._auto_detect = server_name is None
        effective_server = server_name or "langchain"

        super().__init__(
            client=client,
            server_name=effective_server,
            agent_name=agent_name,
            session_id=session_id,
        )
        self._trace_id = trace_id

        # --- Tool call tracking ---
        # run_id → _PendingTool
        self._pending: dict[str, _PendingTool] = {}

        # --- Chain/agent tracking ---
        # run_id → _ActiveChain
        self._active_chains: dict[str, _ActiveChain] = {}

        # --- Cross-ainvoke parent linking (thread-local) ---
        self._local = threading.local()

        # --- LLM call tracking (for token/cost capture) ---
        # run_id → dict with started_at, messages_str, model_name
        self._pending_llm: dict[str, dict[str, Any]] = {}

        # --- LangGraph node deduplication ---
        self._active_lg_nodes: set[str] = set()

        # --- Prompt / answer capture ---
        self._session_input: str | None = None
        self._session_output: str | None = None
        self._session_input_captured = False

        # --- Tier 2: LangGraph loop detection ---
        self._max_node_iterations = max_node_iterations
        self._node_counter: dict[str, int] = {}

        # --- Tier 2: Budget enforcement ---
        self._budget = budget
        self._pricing_table = pricing_table or {}
        self._budget_violated: bool = False
        self._budget_violation: Any = None

    # --- Thread-local tool stack (shared across all callback instances) ---

    @property
    def _tool_stack(self) -> list[_ToolExecContext]:
        """Module-level thread-local stack of currently executing tools.

        Shared across ALL callback instances so cross-ainvoke parent linking
        works even when each sub-agent gets its own callback (the common
        LangGraph pattern).
        """
        return _get_global_tool_stack()

    # --- Public API: prompt / answer capture ---

    def set_input(self, text: str) -> None:
        """Explicitly set the session input (human prompt).

        Overrides auto-capture from on_chat_model_start.
        """
        self._session_input = text
        self._session_input_captured = True

    def set_output(self, text: str) -> None:
        """Explicitly set the session output (agent's final answer)."""
        self._session_output = text

    # --- Resolving parent span ---

    def _resolve_parent_span_id(self, parent_run_id: UUID | None) -> str | None:
        """Find the parent_span_id for a new span.

        Priority:
        1. parent_run_id maps to a known agent chain → use that agent's span_id
        2. Tool execution stack is non-empty → cross-ainvoke link to executing tool
        3. None (root span)
        """
        if parent_run_id:
            chain = self._active_chains.get(str(parent_run_id))
            if chain and chain.agent_span_id:
                return chain.agent_span_id

        # Cross-ainvoke: a tool is executing and a new chain just started inside it
        stack = self._tool_stack
        if stack:
            return stack[-1].span_id

        return None

    def _find_enclosing_agent(self, parent_run_id: UUID | None) -> tuple[str | None, str | None]:
        """Find the enclosing agent name and span_id for a tool call.

        Walks up the chain hierarchy via parent_run_id to find the nearest
        agent chain. Returns (agent_name, agent_span_id).

        Falls back to self._agent_name when no chain context is available
        (e.g. LangGraph v1.0 which doesn't fire on_chain_start for graph
        execution — it only fires tool and LLM callbacks).
        """
        if parent_run_id:
            chain = self._active_chains.get(str(parent_run_id))
            if chain and chain.is_agent:
                return chain.name, chain.agent_span_id

        # No agent chain found — fall back to constructor agent_name.
        # This ensures LangGraph and other frameworks that don't fire
        # on_chain_start still get agent_name on their tool spans.
        return self._agent_name, None

    # -----------------------------------------------------------------------
    # LangChain callback interface — chain lifecycle (agent detection)
    # -----------------------------------------------------------------------

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Track chain starts. Named agents get span_type='agent' spans."""
        if not self._auto_detect:
            return  # Fixed mode — skip chain tracking

        # --- Tier 2: Budget violation flag check (set in on_llm_end) ---
        if self._budget_violated and self._budget_violation is not None:
            from langsight.exceptions import BudgetExceededError

            violation = self._budget_violation
            raise BudgetExceededError(
                limit_type=violation.limit_type,
                limit_value=violation.limit_value,
                actual_value=violation.actual_value,
                session_id=self._session_id,
            )

        agent_name = _detect_agent_name(serialized, metadata)
        key = str(run_id)

        if agent_name:
            # Determine whether this is a LangGraph node (vs a named graph/chain).
            # A node comes from metadata["langgraph_node"]; a graph comes from
            # serialized["name"] (e.g. "LangGraph") when serialized is not None.
            is_node = bool((metadata or {}).get("langgraph_node")) and (
                not serialized or not serialized.get("name")
            )

            # Deduplication: skip duplicate on_chain_start for same LangGraph node
            node_from_meta = (metadata or {}).get("langgraph_node")
            if (
                node_from_meta
                and agent_name == node_from_meta
                and agent_name in self._active_lg_nodes
            ):
                self._active_chains[key] = _ActiveChain(
                    name=agent_name,
                    started_at=datetime.now(UTC),
                    is_agent=False,
                )
                return

            # --- Tier 2: Node iteration counting ---
            if node_from_meta and agent_name == node_from_meta:
                count = self._node_counter.get(agent_name, 0) + 1
                self._node_counter[agent_name] = count
                if self._max_node_iterations > 0 and count > self._max_node_iterations:
                    logger.warning(
                        "integration.node_iteration_limit",
                        node=agent_name,
                        count=count,
                        max=self._max_node_iterations,
                        session_id=self._session_id,
                    )
                    # Emit a prevented span
                    try:
                        if self._client is not None:
                            self._client.buffer_span(
                                ToolCallSpan(
                                    server_name="langgraph",
                                    tool_name=agent_name,
                                    started_at=datetime.now(UTC),
                                    ended_at=datetime.now(UTC),
                                    status=ToolCallStatus.PREVENTED,
                                    error=f"node_iteration_limit: {agent_name} ran {count} times (limit: {self._max_node_iterations})",
                                    session_id=self._session_id,
                                    trace_id=self._trace_id,
                                    span_type="node",
                                    project_id=getattr(self._client, "_project_id", None) or "",
                                )
                            )
                    except Exception:  # noqa: BLE001
                        pass
                    from langsight.exceptions import GraphLoopDetectedError

                    raise GraphLoopDetectedError(
                        node_name=agent_name,
                        iteration_count=count,
                        max_iterations=self._max_node_iterations,
                        session_id=self._session_id,
                    )

            span_id = str(uuid.uuid4())
            parent = self._resolve_parent_span_id(parent_run_id)

            input_data: dict[str, Any] | None = None
            if not self._redact and isinstance(inputs, dict):
                input_data = inputs

            self._active_chains[key] = _ActiveChain(
                name=agent_name,
                started_at=datetime.now(UTC),
                is_agent=True,
                agent_span_id=span_id,
                parent_span_id=parent,
                is_langgraph_node=is_node,
                input_data=input_data,
            )

            if node_from_meta and agent_name == node_from_meta:
                self._active_lg_nodes.add(agent_name)

            logger.debug(
                "integration.agent_detected",
                agent=agent_name,
                span_id=span_id,
                parent_span_id=parent,
                is_node=is_node,
            )
        else:
            # Track non-agent chains for node context (like langgraph.py did)
            node_name = (
                (metadata or {}).get("langgraph_node")
                or (serialized or {}).get("name")
                or (serialized or {}).get("id", ["unknown"])[-1]
                or "unknown"
            )
            self._active_chains[key] = _ActiveChain(
                name=node_name,
                started_at=datetime.now(UTC),
                is_agent=False,
            )

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Finalize agent spans when a chain ends."""
        key = str(run_id)
        chain = self._active_chains.pop(key, None)
        if not chain or not chain.is_agent:
            return

        if chain.is_langgraph_node:
            self._active_lg_nodes.discard(chain.name)

        # LangGraph nodes are discrete workflow steps — span_type='node'.
        # Graph roots, session wrappers, and LLM spans stay as span_type='agent'.
        span_type: SpanType = "node" if chain.is_langgraph_node else "agent"

        input_args: dict[str, Any] | None = None
        output_result: str | None = None
        if not self._redact:
            input_args = chain.input_data
            if isinstance(outputs, dict):
                output_result = _safe_json(outputs)
            elif outputs is not None:
                output_result = _truncate(str(outputs))

        ended_at = datetime.now(UTC)
        span = ToolCallSpan(
            span_id=chain.agent_span_id or str(uuid.uuid4()),
            server_name=chain.name,
            tool_name="run",
            started_at=chain.started_at,
            ended_at=ended_at,
            status=ToolCallStatus.SUCCESS,
            agent_name=chain.name,
            session_id=self._session_id,
            trace_id=self._trace_id,
            parent_span_id=chain.parent_span_id,
            span_type=span_type,
            project_id=getattr(self._client, "_project_id", None) or "",
            input_args=input_args,
            output_result=output_result,
        )
        self._client.buffer_span(span)  # type: ignore[union-attr]
        _try_flush(self._client)
        logger.debug(
            "integration.agent_span_emitted",
            agent=chain.name,
            latency_ms=span.latency_ms,
        )

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Emit agent span with error status on chain failure."""
        key = str(run_id)
        chain = self._active_chains.pop(key, None)
        if not chain or not chain.is_agent:
            return

        if chain.is_langgraph_node:
            self._active_lg_nodes.discard(chain.name)

        span_type: SpanType = "node" if chain.is_langgraph_node else "agent"

        ended_at = datetime.now(UTC)
        span = ToolCallSpan(
            span_id=chain.agent_span_id or str(uuid.uuid4()),
            server_name=chain.name,
            tool_name="run",
            started_at=chain.started_at,
            ended_at=ended_at,
            status=ToolCallStatus.ERROR,
            error=str(error),
            agent_name=chain.name,
            session_id=self._session_id,
            trace_id=self._trace_id,
            parent_span_id=chain.parent_span_id,
            span_type=span_type,
            project_id=getattr(self._client, "_project_id", None) or "",
        )
        self._client.buffer_span(span)  # type: ignore[union-attr]
        _try_flush(self._client)

    # -----------------------------------------------------------------------
    # LangChain callback interface — tool lifecycle
    # -----------------------------------------------------------------------

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when a LangChain tool call begins."""
        tool_name = serialized.get("name") or serialized.get("id", ["unknown"])[-1] or "unknown"
        key = str(run_id)

        # Pre-generate span_id so sub-agents can reference it as parent
        span_id = str(uuid.uuid4())

        # Resolve enclosing agent and parent span
        agent_name, parent_span_id = self._find_enclosing_agent(parent_run_id)
        if not parent_span_id:
            # Check global tool stack for cross-ainvoke parent (works in both modes)
            parent_span_id = self._resolve_parent_span_id(parent_run_id)

        self._pending[key] = _PendingTool(
            tool_name=tool_name,
            started_at=datetime.now(UTC),
            input_str=input_str,
            span_id=span_id,
            agent_name=agent_name,
            parent_span_id=parent_span_id,
        )

        # Push to cross-ainvoke stack so sub-agents can link to this tool
        self._tool_stack.append(
            _ToolExecContext(
                run_id=key,
                span_id=span_id,
                tool_name=tool_name,
            )
        )

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Called when a LangChain tool call completes successfully."""
        key = str(run_id)
        pending = self._pending.pop(key, None)
        if not pending:
            return

        # Pop from cross-ainvoke stack
        stack = self._tool_stack
        if stack and stack[-1].run_id == key:
            stack.pop()

        self._record(
            tool_name=pending.tool_name,
            started_at=pending.started_at,
            status=ToolCallStatus.SUCCESS,
            trace_id=self._trace_id,
            input_str=pending.input_str,
            output=output,
            parent_span_id=pending.parent_span_id,
            agent_name=pending.agent_name,
            span_id=pending.span_id,
        )
        _try_flush(self._client)

    def on_tool_error(
        self,
        error: BaseException | Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Called when a LangChain tool call raises an error."""
        key = str(run_id)
        pending = self._pending.pop(key, None)
        if not pending:
            return

        # Pop from cross-ainvoke stack
        stack = self._tool_stack
        if stack and stack[-1].run_id == key:
            stack.pop()

        self._record(
            tool_name=pending.tool_name,
            started_at=pending.started_at,
            status=ToolCallStatus.ERROR,
            error=str(error),
            trace_id=self._trace_id,
            input_str=pending.input_str,
            parent_span_id=pending.parent_span_id,
            agent_name=pending.agent_name,
            span_id=pending.span_id,
        )
        _try_flush(self._client)

    # -----------------------------------------------------------------------
    # LangChain callback interface — LLM lifecycle (prompt capture)
    # -----------------------------------------------------------------------

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Capture LLM call start time, messages, and model name."""
        key = str(run_id)

        # Extract model name from serialized
        model_name: str | None = None
        try:
            kw = (serialized or {}).get("kwargs", {})
            model_name = kw.get("model") or kw.get("model_name")
            if not model_name:
                model_name = (serialized or {}).get("model") or (serialized or {}).get("model_name")
        except (AttributeError, TypeError):
            pass

        # Serialize messages for llm_input
        messages_str: str | None = None
        if not self._redact:
            try:
                messages_str = _serialize_messages(messages)
            except Exception:  # noqa: BLE001
                pass

        # Store in _pending_llm (fixes 0ms latency for chat models)
        self._pending_llm[key] = {
            "started_at": datetime.now(UTC),
            "messages_str": messages_str,
            "model_name": model_name,
        }

        # Session input auto-capture (existing behavior)
        if self._session_input_captured:
            return
        try:
            for msg in messages[0]:
                msg_type = getattr(msg, "type", None)
                if msg_type == "human":
                    content = getattr(msg, "content", None)
                    if content and isinstance(content, str):
                        self._session_input = content
                        self._session_input_captured = True
                        logger.debug("integration.prompt_captured", length=len(content))
                        return
        except (IndexError, TypeError, AttributeError):
            pass

    def on_llm_start(self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any) -> None:
        """Record LLM call start time for completion models."""
        run_id = kwargs.get("run_id")
        if run_id:
            key = str(run_id)
            if key not in self._pending_llm:
                model_name: str | None = None
                try:
                    kw = (serialized or {}).get("kwargs", {})
                    model_name = kw.get("model") or kw.get("model_name")
                except (AttributeError, TypeError):
                    pass
                messages_str: str | None = None
                if not self._redact and prompts:
                    messages_str = _truncate("\n".join(prompts))
                self._pending_llm[key] = {
                    "started_at": datetime.now(UTC),
                    "messages_str": messages_str,
                    "model_name": model_name,
                }

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        """Extract tokens, model, LLM I/O from response -> emit agent span."""
        run_id = kwargs.get("run_id")
        pending_data = self._pending_llm.pop(str(run_id), None) if run_id else None

        if pending_data:
            started_at = pending_data.get("started_at", datetime.now(UTC))
            stored_messages = pending_data.get("messages_str")
            stored_model = pending_data.get("model_name")
        else:
            started_at = datetime.now(UTC)
            stored_messages = None
            stored_model = None

        input_tokens: int | None = None
        output_tokens: int | None = None
        thinking_tokens: int | None = None
        model_id: str | None = stored_model
        llm_output_text: str | None = None
        finish_reason: str | None = None

        try:
            generations = getattr(response, "generations", None) or []
            for gen_list in generations:
                for gen in gen_list:
                    msg = getattr(gen, "message", None)
                    um = getattr(msg, "usage_metadata", None) if msg else None
                    if um and isinstance(um, dict):
                        input_tokens = um.get("input_tokens")
                        output_tokens = um.get("output_tokens")
                        # Extract thinking tokens for models that provide total_tokens
                        # (Gemini: thinking = total - input - output)
                        total_tokens_raw = um.get("total_tokens")
                        if (
                            total_tokens_raw
                            and input_tokens is not None
                            and output_tokens is not None
                        ):
                            thinking = total_tokens_raw - input_tokens - output_tokens
                            if thinking > 0:
                                thinking_tokens = thinking

                    gi = getattr(gen, "generation_info", None)
                    if gi and isinstance(gi, dict):
                        gi_model = gi.get("model_name")
                        if gi_model:
                            model_id = gi_model
                        if not finish_reason:
                            finish_reason = gi.get("finish_reason")

                    if not self._redact and llm_output_text is None:
                        msg_content = getattr(msg, "content", None) if msg else None
                        if msg_content and isinstance(msg_content, str):
                            llm_output_text = _truncate(msg_content)
                        elif hasattr(gen, "text") and gen.text:
                            llm_output_text = _truncate(gen.text)

                    if input_tokens is not None:
                        break
                if input_tokens is not None:
                    break
        except (AttributeError, TypeError, IndexError):
            pass

        if not model_id:
            try:
                llm_out = getattr(response, "llm_output", None)
                if llm_out and isinstance(llm_out, dict):
                    model_id = llm_out.get("model") or llm_out.get("model_name")
            except (AttributeError, TypeError):
                pass

        if input_tokens is None and output_tokens is None:
            return

        # --- Tier 2: Budget enforcement ---
        if self._budget is not None and input_tokens is not None:
            cost_usd = 0.0
            _mid = model_id or ""
            # Try exact match, then strip provider prefix
            pricing = self._pricing_table.get(_mid)
            if not pricing:
                for prefix in ("models/", "anthropic/", "openai/", "google/", "meta/"):
                    if _mid.startswith(prefix):
                        pricing = self._pricing_table.get(_mid[len(prefix) :])
                        break
            if pricing:
                cost_usd = (input_tokens or 0) / 1_000_000 * pricing[0] + (
                    output_tokens or 0
                ) / 1_000_000 * pricing[1]
            else:
                # Conservative fallback
                cost_usd = (input_tokens or 0) / 1_000_000 * 10.0 + (
                    output_tokens or 0
                ) / 1_000_000 * 30.0

            violation = self._budget.record_step_and_cost(cost_usd)
            if violation is not None:
                logger.warning(
                    "integration.budget_exceeded",
                    limit_type=violation.limit_type,
                    actual=violation.actual_value,
                    limit=violation.limit_value,
                    session_id=self._session_id,
                )
                # Set flag — exception raised on next on_chain_start
                # (LangChain swallows exceptions from on_llm_end)
                self._budget_violated = True
                self._budget_violation = violation
                # Emit prevented span
                try:
                    if self._client is not None:
                        self._client.buffer_span(
                            ToolCallSpan(
                                server_name="langgraph",
                                tool_name="budget_exceeded",
                                started_at=datetime.now(UTC),
                                ended_at=datetime.now(UTC),
                                status=ToolCallStatus.PREVENTED,
                                error=f"budget_exceeded: {violation.limit_type}={violation.actual_value} (limit: {violation.limit_value})",
                                session_id=self._session_id,
                                trace_id=self._trace_id,
                                span_type="agent",
                                project_id=getattr(self._client, "_project_id", None) or "",
                            )
                        )
                except Exception:  # noqa: BLE001
                    pass

        parent_run_id = kwargs.get("parent_run_id")
        agent_name = self._agent_name
        parent_span_id: str | None = None
        if parent_run_id:
            chain = self._active_chains.get(str(parent_run_id))
            if chain and chain.is_agent:
                agent_name = chain.name
                parent_span_id = chain.agent_span_id

        server_name = model_id or "llm"
        tool_name = f"generate/{model_id}" if model_id else "generate"

        span = ToolCallSpan.record(
            server_name=server_name,
            tool_name=tool_name,
            started_at=started_at,
            status=ToolCallStatus.SUCCESS,
            agent_name=agent_name,
            session_id=self._session_id,
            trace_id=self._trace_id,
            parent_span_id=parent_span_id,
            span_type="agent",
            project_id=getattr(self._client, "_project_id", None) or "",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thinking_tokens=thinking_tokens,
            model_id=model_id,
            llm_input=stored_messages,
            llm_output=llm_output_text,
            finish_reason=finish_reason,
        )
        self._client.buffer_span(span)  # type: ignore[union-attr]
        _try_flush(self._client)
        logger.debug(
            "integration.llm_span_emitted",
            model=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
