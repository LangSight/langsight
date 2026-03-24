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
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog

from langsight.integrations.base import BaseIntegration
from langsight.sdk.client import LangSightClient
from langsight.sdk.models import ToolCallSpan, ToolCallStatus

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Agent detection — skip framework-internal chain names
# ---------------------------------------------------------------------------

_SKIP_CHAIN_NAMES = frozenset({
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
})

# LangGraph internal node names (not user-defined agents)
_SKIP_NODE_NAMES = frozenset({
    "tools",
    "tool_node",
    "__start__",
    "__end__",
    "should_continue",
    "agent",  # internal react-agent node, not the graph itself
})


def _detect_agent_name(
    serialized: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> str | None:
    """Return agent name if this chain_start is a named agent, else None.

    Heuristic: a chain is an agent if it has a user-defined name that is
    not a framework-internal class or LangGraph internal node.
    """
    name = serialized.get("name", "")
    if not name or name in _SKIP_CHAIN_NAMES:
        return None

    # LangGraph internal nodes appear in metadata
    node = (metadata or {}).get("langgraph_node")
    if node and node in _SKIP_NODE_NAMES:
        return None

    # Heuristic: framework class names are CamelCase, user names are lowercase
    # But don't be too strict — "MyAgent" is a valid user name
    # The _SKIP sets above catch the common framework names
    return name


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
        _global_tool_stack_local.stack: list[_ToolExecContext] = []
    return _global_tool_stack_local.stack


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fire_and_forget(coro: Any) -> None:
    """Schedule a coroutine from a synchronous LangChain callback.

    Tries create_task if a loop is already running and not closing (async context).
    Falls back to running in a daemon thread (sync/test context or loop teardown)
    to avoid 'coroutine was never awaited' and 'Event loop is closed' warnings.
    """
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running() and not loop.is_closed():
            loop.create_task(coro)
            return
    except RuntimeError:
        pass
    thread = threading.Thread(target=asyncio.run, args=(coro,), daemon=True)
    thread.start()


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
                from langchain.callbacks.base import BaseCallbackHandler  # type: ignore[no-redef]

            self.__class__.__bases__ = (BaseIntegration, BaseCallbackHandler)
            BaseCallbackHandler.__init__(self)
        except ImportError:
            logger.warning(
                "langchain-core not installed. Install with: pip install langchain-core"
            )

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
        # run_id → started_at
        self._pending_llm: dict[str, datetime] = {}

        # --- Prompt / answer capture ---
        self._session_input: str | None = None
        self._session_output: str | None = None
        self._session_input_captured = False

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

        agent_name = _detect_agent_name(serialized, metadata)
        key = str(run_id)

        if agent_name:
            # This is a named agent — emit an agent span
            span_id = str(uuid.uuid4())
            parent = self._resolve_parent_span_id(parent_run_id)

            self._active_chains[key] = _ActiveChain(
                name=agent_name,
                started_at=datetime.now(UTC),
                is_agent=True,
                agent_span_id=span_id,
                parent_span_id=parent,
            )
            logger.debug(
                "integration.agent_detected",
                agent=agent_name,
                span_id=span_id,
                parent_span_id=parent,
            )
        else:
            # Track non-agent chains for node context (like langgraph.py did)
            node_name = serialized.get("name") or serialized.get("id", ["unknown"])[-1] or "unknown"
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

        # Emit the finalized agent span (use constructor directly for span_id)
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
            span_type="agent",
            project_id=getattr(self._client, "_project_id", None) or "",
        )
        _fire_and_forget(self._client.send_span(span))
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
            span_type="agent",
            project_id=getattr(self._client, "_project_id", None) or "",
        )
        _fire_and_forget(self._client.send_span(span))

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
        self._tool_stack.append(_ToolExecContext(
            run_id=key,
            span_id=span_id,
            tool_name=tool_name,
        ))

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

        _fire_and_forget(
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
        )

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

        _fire_and_forget(
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
        )

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
        """Capture the first human message as session input (auto-capture)."""
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
            pass  # Defensive — don't crash on unexpected message format

    def on_llm_start(
        self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any
    ) -> None:
        """Record LLM call start time for token/cost tracking."""
        run_id = kwargs.get("run_id")
        if run_id:
            self._pending_llm[str(run_id)] = datetime.now(UTC)

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        """Extract token counts and model from LLM response → emit agent span.

        LangChain passes token usage in:
        - response.generations[0][0].message.usage_metadata (Gemini, OpenAI)
        - response.generations[0][0].generation_info["model_name"]
        """
        run_id = kwargs.get("run_id")
        started_at = self._pending_llm.pop(str(run_id), None) if run_id else None
        if started_at is None:
            started_at = datetime.now(UTC)

        # Extract token counts + model from the LLM response
        input_tokens: int | None = None
        output_tokens: int | None = None
        model_id: str | None = None

        try:
            generations = getattr(response, "generations", None) or []
            for gen_list in generations:
                for gen in gen_list:
                    # Token usage from message.usage_metadata
                    msg = getattr(gen, "message", None)
                    um = getattr(msg, "usage_metadata", None) if msg else None
                    if um and isinstance(um, dict):
                        input_tokens = um.get("input_tokens")
                        output_tokens = um.get("output_tokens")

                    # Model name from generation_info
                    gi = getattr(gen, "generation_info", None)
                    if gi and isinstance(gi, dict):
                        model_id = gi.get("model_name")

                    if input_tokens is not None:
                        break  # found tokens, stop searching
                if input_tokens is not None:
                    break
        except (AttributeError, TypeError, IndexError):
            pass  # Defensive — don't crash on unexpected response

        if input_tokens is None and output_tokens is None:
            return  # No token data — skip (avoid noisy empty spans)

        # Resolve agent name from the enclosing context
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
            model_id=model_id,
        )
        _fire_and_forget(self._client.send_span(span))
        logger.debug(
            "integration.llm_span_emitted",
            model=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
