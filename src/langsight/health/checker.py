from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog

from langsight.exceptions import MCPConnectionError, MCPTimeoutError
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
                    server.name, schema_hash, len(tools), current_tools=tools
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
                if upsert_fn:
                    await upsert_fn(
                        server_name=server.name,
                        transport=server.transport.value,
                        project_id=self._project_id or None,
                    )

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

    async def check_many(
        self,
        servers: list[MCPServer],
        global_timeout: float = 60.0,
    ) -> list[HealthCheckResult]:
        """Check multiple MCP servers concurrently with a global timeout backstop.

        Individual server timeouts are configured per-server (MCPServer.timeout_seconds).
        The global_timeout prevents the entire batch from hanging if a server ignores
        its per-check timeout (e.g., a deadlocked MCP process).
        """
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*[self.check(server) for server in servers]),
                timeout=global_timeout,
            )
            return list(results)
        except TimeoutError:
            logger.error(
                "health_checker.global_timeout", timeout=global_timeout, servers=len(servers)
            )
            # Return DOWN results for all servers
            now = datetime.now(UTC)
            return [
                HealthCheckResult(
                    server_name=s.name,
                    status=ServerStatus.DOWN,
                    latency_ms=None,
                    tools_count=0,
                    schema_hash=None,
                    error=f"global timeout ({global_timeout}s)",
                    checked_at=now,
                )
                for s in servers
            ]
