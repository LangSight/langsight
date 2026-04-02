from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog

from langsight.exceptions import MCPConnectionError, MCPHealthToolError, MCPTimeoutError
from langsight.health.schema_tracker import SchemaTracker
from langsight.health.transports import hash_tools, ping
from langsight.models import HealthCheckResult, MCPServer, ServerStatus
from langsight.storage.base import StorageBackend

logger = structlog.get_logger()


class HealthChecker:
    """Checks MCP server health: availability, latency, and tool schema drift.

    Args:
        storage: Optional storage backend. When provided, every result is
                 persisted and schema drift is detected across runs.
                 When None, checks are stateless (no history, no drift detection).
    """

    def __init__(
        self,
        storage: StorageBackend | None = None,
        project_id: str = "",
    ) -> None:
        self._storage = storage
        self._project_id = project_id
        self._schema_tracker = SchemaTracker(storage) if storage else None

    async def check(self, server: MCPServer) -> HealthCheckResult:
        """Run a single health check against one MCP server.

        Always returns a HealthCheckResult — never raises. Errors are captured
        in the result's `status` (DOWN) and `error` fields.
        """
        logger.info("health_check.start", server=server.name, transport=server.transport)

        try:
            latency_ms, tools = await ping(server)
            schema_hash = hash_tools(tools)

            status = ServerStatus.UP
            drift_warning: str | None = None

            # Schema drift detection (only when storage is available)
            if self._schema_tracker:
                drift = await self._schema_tracker.check_and_update(
                    server.name,
                    schema_hash,
                    len(tools),
                    current_tools=tools,
                    project_id=self._project_id,
                )
                if drift.drifted:
                    status = ServerStatus.DEGRADED
                    severity = "BREAKING" if drift.has_breaking else "compatible"
                    drift_warning = (
                        f"schema drift ({severity}): "
                        f"{drift.previous_hash} → {drift.current_hash}"
                        + (f" — {len(drift.changes)} change(s)" if drift.changes else "")
                    )

            result = HealthCheckResult(
                server_name=server.name,
                status=status,
                latency_ms=round(latency_ms, 2),
                tools=tools,
                tools_count=len(tools),
                schema_hash=schema_hash,
                checked_at=datetime.now(UTC),
                error=drift_warning,
                project_id=self._project_id,
            )

            logger.info(
                "health_check.ok",
                server=server.name,
                status=status,
                latency_ms=result.latency_ms,
                tools=result.tools_count,
            )

            # Persist result + register server in metadata (for dashboard MCP Servers page)
            if self._storage:
                await self._storage.save_health_result(result)
                upsert_fn = getattr(self._storage, "upsert_server_metadata", None)
                if upsert_fn and asyncio.iscoroutinefunction(upsert_fn):
                    await upsert_fn(
                        server_name=server.name,
                        transport=server.transport.value,
                        project_id=self._project_id or None,
                    )
                # Persist tool catalog so the dashboard Tools tab always shows
                # current tools — not just on first run or schema drift.
                upsert_tools_fn = getattr(self._storage, "upsert_server_tools", None)
                if upsert_tools_fn and asyncio.iscoroutinefunction(upsert_tools_fn) and tools:
                    tool_dicts = [
                        {
                            "name": t.name,
                            "description": t.description or "",
                            "input_schema": t.input_schema
                            or {},  # dict — upsert_server_tools encodes
                        }
                        for t in tools
                    ]
                    await upsert_tools_fn(
                        server.name,
                        tool_dicts,
                        project_id=self._project_id or None,
                    )

            return result

        except MCPHealthToolError as exc:
            logger.warning(
                "health_check.backend_degraded",
                server=server.name,
                health_tool=server.health_tool,
                error=str(exc),
            )
            result = HealthCheckResult(
                server_name=server.name,
                status=ServerStatus.DEGRADED,  # MCP layer UP, backend DOWN
                checked_at=datetime.now(UTC),
                error=str(exc),
                project_id=self._project_id,
            )
            if self._storage:
                await self._storage.save_health_result(result)
            return result

        except MCPTimeoutError as exc:
            logger.warning("health_check.timeout", server=server.name, error=str(exc))
            result = HealthCheckResult(
                server_name=server.name,
                status=ServerStatus.DOWN,
                checked_at=datetime.now(UTC),
                error=f"timeout after {server.timeout_seconds}s",
                project_id=self._project_id,
            )
            if self._storage:
                await self._storage.save_health_result(result)
            return result

        except MCPConnectionError as exc:
            logger.error("health_check.connection_error", server=server.name, error=str(exc))
            result = HealthCheckResult(
                server_name=server.name,
                status=ServerStatus.DOWN,
                checked_at=datetime.now(UTC),
                error=str(exc),
                project_id=self._project_id,
            )
            if self._storage:
                await self._storage.save_health_result(result)
            return result

        except Exception as exc:  # noqa: BLE001
            logger.error("health_check.unexpected_error", server=server.name, error=str(exc))
            result = HealthCheckResult(
                server_name=server.name,
                status=ServerStatus.DOWN,
                checked_at=datetime.now(UTC),
                error=f"unexpected error: {exc}",
                project_id=self._project_id,
            )
            if self._storage:
                await self._storage.save_health_result(result)
            return result

    # Limit concurrent health checks to avoid spawning hundreds of subprocesses
    # (stdio transport) or opening too many HTTP connections simultaneously.
    # At N=10, 100 servers finish in ~10 batches of 10 — still fast, but safe.
    _CONCURRENCY = 10

    async def check_many(
        self,
        servers: list[MCPServer],
        global_timeout: float = 60.0,
    ) -> list[HealthCheckResult]:
        """Check multiple MCP servers concurrently with a global timeout backstop.

        Individual server timeouts are configured per-server (MCPServer.timeout_seconds).
        The global_timeout prevents the entire batch from hanging if a server ignores
        its per-check timeout (e.g., a deadlocked MCP process).
        A semaphore caps concurrency at _CONCURRENCY to prevent spawning unbounded
        subprocesses when many servers are configured.
        """
        if not servers:
            return []

        sem = asyncio.Semaphore(self._CONCURRENCY)

        async def _bounded_check(server: MCPServer) -> HealthCheckResult:
            async with sem:
                return await self.check(server)

        # Use asyncio.wait() with a timeout so completed checks are not thrown away.
        # Previously asyncio.wait_for() cancelled all pending tasks on timeout,
        # marking every server DOWN — causing alert storms when a single slow
        # server stalled the batch.  Now: already-completed checks are returned;
        # only the still-pending ones get the DOWN result.
        tasks = {asyncio.ensure_future(_bounded_check(s)): s for s in servers}
        done, pending = await asyncio.wait(tasks.keys(), timeout=global_timeout)

        if pending:
            logger.warning(
                "health_checker.partial_timeout",
                timeout=global_timeout,
                completed=len(done),
                timed_out=len(pending),
            )
            now = datetime.now(UTC)
            timeout_results: list[HealthCheckResult] = []
            for task in pending:
                task.cancel()
                server = tasks[task]
                timeout_results.append(
                    HealthCheckResult(
                        server_name=server.name,
                        status=ServerStatus.DOWN,
                        latency_ms=None,
                        tools_count=0,
                        schema_hash=None,
                        error=f"global timeout ({global_timeout}s)",
                        checked_at=now,
                        project_id=self._project_id,
                    )
                )
        else:
            timeout_results = []

        completed_results = [t.result() for t in done if not t.exception()]
        return completed_results + timeout_results
