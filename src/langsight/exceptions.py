from __future__ import annotations


class LangSightError(Exception):
    """Base exception for all LangSight errors."""


class MCPConnectionError(LangSightError):
    """Failed to establish a connection to an MCP server."""


class MCPTimeoutError(MCPConnectionError):
    """Connection to an MCP server timed out."""


class MCPProtocolError(LangSightError):
    """Unexpected MCP protocol response — likely a server-side bug."""


class MCPHealthToolError(MCPConnectionError):
    """Health probe tool call failed — MCP server up but backend is degraded.

    The MCP server responded to initialize + tools/list, but the configured
    health_tool either wasn't found or returned an error. This means the MCP
    layer is alive but the underlying service (e.g. DataHub, Postgres) is down.
    """


class ConfigError(LangSightError):
    """Invalid or missing LangSight configuration."""


class SchemaChangedError(LangSightError):
    """An MCP server's tool schema changed since the last recorded snapshot."""

    def __init__(self, server_name: str, old_hash: str, new_hash: str) -> None:
        self.server_name = server_name
        self.old_hash = old_hash
        self.new_hash = new_hash
        super().__init__(f"Schema changed for '{server_name}': {old_hash} → {new_hash}")


# ---------------------------------------------------------------------------
# v0.3 Prevention layer exceptions
# ---------------------------------------------------------------------------


class LoopDetectedError(LangSightError):
    """Agent loop detected — same tool+args repeated beyond threshold."""

    def __init__(
        self,
        tool_name: str,
        loop_count: int,
        args_hash: str,
        pattern: str,
        session_id: str | None = None,
    ) -> None:
        self.tool_name = tool_name
        self.loop_count = loop_count
        self.args_hash = args_hash
        self.pattern = pattern
        self.session_id = session_id
        super().__init__(
            f"Loop detected on '{tool_name}': {pattern} "
            f"({loop_count} repetitions, args_hash={args_hash})"
        )

    def __reduce__(
        self,
    ) -> tuple[type[LoopDetectedError], tuple[str, int, str, str, str | None]]:
        return (
            self.__class__,
            (self.tool_name, self.loop_count, self.args_hash, self.pattern, self.session_id),
        )


class BudgetExceededError(LangSightError):
    """Session budget limit exceeded (cost, steps, or wall time)."""

    def __init__(
        self,
        limit_type: str,
        limit_value: float,
        actual_value: float,
        session_id: str | None = None,
    ) -> None:
        self.limit_type = limit_type
        self.limit_value = limit_value
        self.actual_value = actual_value
        self.session_id = session_id
        super().__init__(
            f"Budget exceeded: {limit_type} limit is {limit_value}, actual is {actual_value}"
        )

    def __reduce__(
        self,
    ) -> tuple[type[BudgetExceededError], tuple[str, float, float, str | None]]:
        return (
            self.__class__,
            (self.limit_type, self.limit_value, self.actual_value, self.session_id),
        )


class CircuitBreakerOpenError(LangSightError):
    """Circuit breaker is open — tool calls rejected without hitting server."""

    def __init__(self, server_name: str, cooldown_remaining_s: float) -> None:
        self.server_name = server_name
        self.cooldown_remaining_s = cooldown_remaining_s
        super().__init__(
            f"Circuit breaker open for '{server_name}': "
            f"{cooldown_remaining_s:.1f}s remaining in cooldown"
        )

    def __reduce__(
        self,
    ) -> tuple[type[CircuitBreakerOpenError], tuple[str, float]]:
        return (self.__class__, (self.server_name, self.cooldown_remaining_s))
