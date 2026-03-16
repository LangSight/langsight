from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog

from langsight.exceptions import MCPConnectionError, MCPTimeoutError
from langsight.health.transports import hash_tools, ping
from langsight.models import HealthCheckResult, MCPServer, ServerStatus

logger = structlog.get_logger()


class HealthChecker:
    """Checks MCP server health: availability, latency, and tool schema."""

    async def check(self, server: MCPServer) -> HealthCheckResult:
        """Run a single health check against one MCP server.

        Always returns a HealthCheckResult — never raises. Errors are captured
        in the result's `status` (DOWN) and `error` fields.
        """
        logger.info("health_check.start", server=server.name, transport=server.transport)

        try:
            latency_ms, tools = await ping(server)
            schema_hash = hash_tools(tools)

            result = HealthCheckResult(
                server_name=server.name,
                status=ServerStatus.UP,
                latency_ms=round(latency_ms, 2),
                tools=tools,
                tools_count=len(tools),
                schema_hash=schema_hash,
                checked_at=datetime.now(timezone.utc),
            )
            logger.info(
                "health_check.ok",
                server=server.name,
                latency_ms=result.latency_ms,
                tools=result.tools_count,
            )
            return result

        except MCPTimeoutError as exc:
            logger.warning("health_check.timeout", server=server.name, error=str(exc))
            return HealthCheckResult(
                server_name=server.name,
                status=ServerStatus.DOWN,
                checked_at=datetime.now(timezone.utc),
                error=f"timeout after {server.timeout_seconds}s",
            )

        except MCPConnectionError as exc:
            logger.error("health_check.connection_error", server=server.name, error=str(exc))
            return HealthCheckResult(
                server_name=server.name,
                status=ServerStatus.DOWN,
                checked_at=datetime.now(timezone.utc),
                error=str(exc),
            )

        except Exception as exc:  # noqa: BLE001
            logger.error("health_check.unexpected_error", server=server.name, error=str(exc))
            return HealthCheckResult(
                server_name=server.name,
                status=ServerStatus.DOWN,
                checked_at=datetime.now(timezone.utc),
                error=f"unexpected error: {exc}",
            )

    async def check_many(self, servers: list[MCPServer]) -> list[HealthCheckResult]:
        """Check multiple MCP servers concurrently via asyncio.gather."""
        results = await asyncio.gather(*[self.check(server) for server in servers])
        return list(results)
