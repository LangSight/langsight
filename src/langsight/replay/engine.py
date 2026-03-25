"""
Replay engine — re-executes a session's tool calls against live MCP servers.

Design principles:
- Each tool call is re-executed with the exact input_args from the original span.
- Replay spans are stored as a new session (new session_id) with replay_of
  set to the original span_id, enabling compare drawer to diff them.
- Fail-open per span: if one tool call fails or times out, replay continues
  with remaining calls. The failure is recorded in the replay span.
- Hard timeout per span (default 10s) and total timeout (default 60s).
- Requires ClickHouse backend (needs get_session_trace + save_tool_call_spans).
- Requires MCP server configs from LangSightConfig to connect to tool servers.

Usage:
    engine = ReplayEngine(storage, config)
    result = await engine.replay(session_id, timeout_per_call=10, total_timeout=60)
    # result.replay_session_id can be passed to /compare for side-by-side view
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog

from langsight.config import LangSightConfig
from langsight.sdk.models import ToolCallSpan, ToolCallStatus

logger = structlog.get_logger()

DEFAULT_TIMEOUT_PER_CALL = 10.0  # seconds
DEFAULT_TOTAL_TIMEOUT = 60.0  # seconds


@dataclass
class ReplayResult:
    """Result of a replay execution."""

    original_session_id: str
    replay_session_id: str
    total_spans: int
    replayed: int  # spans successfully re-executed
    skipped: int  # spans without input_args (LLM/agent spans)
    failed: int  # spans that errored during replay
    duration_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_session_id": self.original_session_id,
            "replay_session_id": self.replay_session_id,
            "total_spans": self.total_spans,
            "replayed": self.replayed,
            "skipped": self.skipped,
            "failed": self.failed,
            "duration_ms": round(self.duration_ms, 2),
        }


class ReplayEngine:
    """Re-executes a session's tool calls against live MCP servers.

    Only replays tool_call spans that have stored input_args.
    Agent and handoff spans, and any span without input_args, are skipped.
    """

    def __init__(
        self,
        storage: object,
        config: LangSightConfig,
        timeout_per_call: float = DEFAULT_TIMEOUT_PER_CALL,
        total_timeout: float = DEFAULT_TOTAL_TIMEOUT,
    ) -> None:
        self._storage = storage
        self._config = config
        self._timeout_per_call = timeout_per_call
        self._total_timeout = total_timeout

    async def replay(self, session_id: str, project_id: str | None = None) -> ReplayResult:
        """Replay all replayable tool calls from a session.

        project_id is passed through to get_session_trace so the storage layer
        can scope the lookup to the caller's project. Passing None is only safe
        for global admins (the router enforces this via get_active_project_id).

        Returns a ReplayResult. The replay session is stored under a new
        session_id so compare_sessions() can diff original vs replay.
        """
        if not hasattr(self._storage, "get_session_trace"):
            raise RuntimeError("ReplayEngine requires ClickHouse backend.")

        spans = await self._storage.get_session_trace(session_id, project_id=project_id)
        if not spans:
            raise ValueError(f"Session '{session_id}' not found or has no spans.")

        replay_session_id = uuid.uuid4().hex
        started = datetime.now(UTC)

        replayable = [s for s in spans if s.get("span_type") == "tool_call" and s.get("input_json")]
        skipped = len(spans) - len(replayable)

        replay_spans: list[ToolCallSpan] = []
        failed = 0

        try:
            async with asyncio.timeout(self._total_timeout):
                for original in replayable:
                    span = await self._replay_one(
                        original=original,
                        replay_session_id=replay_session_id,
                    )
                    replay_spans.append(span)
                    if span.status != ToolCallStatus.SUCCESS:
                        failed += 1
        except TimeoutError:
            logger.warning(
                "replay.total_timeout",
                session_id=session_id,
                completed=len(replay_spans),
                total=len(replayable),
            )

        if replay_spans and hasattr(self._storage, "save_tool_call_spans"):
            await self._storage.save_tool_call_spans(replay_spans)

        duration_ms = (datetime.now(UTC) - started).total_seconds() * 1000

        logger.info(
            "replay.complete",
            original=session_id,
            replay=replay_session_id,
            replayed=len(replay_spans),
            failed=failed,
            skipped=skipped,
        )

        return ReplayResult(
            original_session_id=session_id,
            replay_session_id=replay_session_id,
            total_spans=len(spans),
            replayed=len(replay_spans),
            skipped=skipped,
            failed=failed,
            duration_ms=duration_ms,
        )

    async def _replay_one(
        self,
        original: dict[str, Any],
        replay_session_id: str,
    ) -> ToolCallSpan:
        """Execute one tool call and return the replay span."""
        server_name: str = original.get("server_name", "unknown")
        tool_name: str = original.get("tool_name", "unknown")
        original_span_id: str = original.get("span_id", "")

        # Deserialise stored input_args
        args: dict[str, Any] | None = None
        raw_input = original.get("input_json")
        if raw_input:
            try:
                args = json.loads(raw_input)
            except (json.JSONDecodeError, TypeError):
                args = None

        started_at = datetime.now(UTC)
        status = ToolCallStatus.SUCCESS
        error: str | None = None
        output_result: str | None = None

        # Find the server config for this tool
        server_config = next(
            (s for s in self._config.servers if s.name == server_name),
            None,
        )

        if server_config is None:
            status = ToolCallStatus.ERROR
            error = f"MCP server '{server_name}' not found in config — cannot replay"
            logger.warning("replay.server_not_configured", server=server_name)
        else:
            try:
                output_result = await asyncio.wait_for(
                    self._call_tool(server_config, tool_name, args or {}),
                    timeout=self._timeout_per_call,
                )
            except TimeoutError:
                status = ToolCallStatus.TIMEOUT
                error = f"Replay timed out after {self._timeout_per_call}s"
                logger.warning("replay.span_timeout", server=server_name, tool=tool_name)
            except Exception as exc:  # noqa: BLE001
                status = ToolCallStatus.ERROR
                error = str(exc)
                logger.warning("replay.span_error", server=server_name, tool=tool_name, error=error)

        return ToolCallSpan.record(
            server_name=server_name,
            tool_name=tool_name,
            started_at=started_at,
            status=status,
            error=error,
            session_id=replay_session_id,
            trace_id=original.get("trace_id") or None,
            agent_name=original.get("agent_name") or None,
            span_type="tool_call",
            input_args=args,
            output_result=output_result,
            replay_of=original_span_id,
        )

    async def _call_tool(
        self,
        server_config: Any,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> str | None:
        """Connect to an MCP server and call a tool. Returns JSON-serialised result."""
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        if server_config.transport.value == "stdio":
            if not server_config.command:
                raise ValueError(f"stdio server '{server_config.name}' has no command configured")

            params = StdioServerParameters(
                command=server_config.command,
                args=list(server_config.args),
                env=dict(server_config.env) if server_config.env else None,
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments)
                    try:
                        return json.dumps(result, default=str)
                    except Exception:  # noqa: BLE001
                        return str(result)

        elif server_config.transport.value in ("sse", "streamable_http"):
            if not server_config.url:
                raise ValueError(f"HTTP server '{server_config.name}' has no URL configured")

            from mcp.client.sse import sse_client

            async with sse_client(server_config.url) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments)
                    try:
                        return json.dumps(result, default=str)
                    except Exception:  # noqa: BLE001
                        return str(result)

        else:
            raise ValueError(f"Unsupported transport: {server_config.transport}")
