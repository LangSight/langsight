from __future__ import annotations

import pytest

from langsight.exceptions import (
    BudgetExceededError,
    CircuitBreakerOpenError,
    ConfigError,
    LangSightError,
    LoopDetectedError,
    MCPConnectionError,
    MCPHealthToolError,
    MCPProtocolError,
    MCPTimeoutError,
    SchemaChangedError,
)


class TestExceptionHierarchy:
    def test_mcp_connection_error_is_langsight_error(self) -> None:
        assert issubclass(MCPConnectionError, LangSightError)

    def test_mcp_timeout_error_is_connection_error(self) -> None:
        assert issubclass(MCPTimeoutError, MCPConnectionError)

    def test_mcp_protocol_error_is_langsight_error(self) -> None:
        assert issubclass(MCPProtocolError, LangSightError)

    def test_config_error_is_langsight_error(self) -> None:
        assert issubclass(ConfigError, LangSightError)

    def test_schema_changed_error_is_langsight_error(self) -> None:
        assert issubclass(SchemaChangedError, LangSightError)


class TestSchemaChangedError:
    def test_stores_server_name(self) -> None:
        err = SchemaChangedError("my-server", "abc123", "def456")
        assert err.server_name == "my-server"

    def test_stores_hashes(self) -> None:
        err = SchemaChangedError("my-server", "abc123", "def456")
        assert err.old_hash == "abc123"
        assert err.new_hash == "def456"

    def test_message_contains_server_name(self) -> None:
        err = SchemaChangedError("my-server", "abc123", "def456")
        assert "my-server" in str(err)

    def test_message_contains_both_hashes(self) -> None:
        err = SchemaChangedError("my-server", "abc123", "def456")
        assert "abc123" in str(err)
        assert "def456" in str(err)

    def test_can_be_raised_and_caught(self) -> None:
        with pytest.raises(SchemaChangedError) as exc_info:
            raise SchemaChangedError("srv", "old", "new")
        assert exc_info.value.server_name == "srv"


class TestLoopDetectedError:
    def test_is_langsight_error(self) -> None:
        assert issubclass(LoopDetectedError, LangSightError)

    def test_stores_attributes(self) -> None:
        err = LoopDetectedError("query", 3, "abc123", "repetition", "sess-1")
        assert err.tool_name == "query"
        assert err.loop_count == 3
        assert err.args_hash == "abc123"
        assert err.pattern == "repetition"
        assert err.session_id == "sess-1"

    def test_message_contains_details(self) -> None:
        err = LoopDetectedError("query", 3, "abc123", "repetition")
        msg = str(err)
        assert "query" in msg
        assert "repetition" in msg
        assert "3" in msg

    def test_session_id_defaults_to_none(self) -> None:
        err = LoopDetectedError("query", 3, "abc123", "repetition")
        assert err.session_id is None

    def test_can_be_raised_and_caught(self) -> None:
        with pytest.raises(LoopDetectedError) as exc_info:
            raise LoopDetectedError("query", 3, "abc", "ping_pong")
        assert exc_info.value.tool_name == "query"


class TestBudgetExceededError:
    def test_is_langsight_error(self) -> None:
        assert issubclass(BudgetExceededError, LangSightError)

    def test_stores_attributes(self) -> None:
        err = BudgetExceededError("max_steps", 25.0, 26.0, "sess-1")
        assert err.limit_type == "max_steps"
        assert err.limit_value == 25.0
        assert err.actual_value == 26.0
        assert err.session_id == "sess-1"

    def test_message_contains_details(self) -> None:
        err = BudgetExceededError("max_cost_usd", 1.0, 1.03)
        msg = str(err)
        assert "max_cost_usd" in msg
        assert "1.0" in msg
        assert "1.03" in msg

    def test_session_id_defaults_to_none(self) -> None:
        err = BudgetExceededError("max_steps", 25.0, 26.0)
        assert err.session_id is None

    def test_can_be_raised_and_caught(self) -> None:
        with pytest.raises(BudgetExceededError) as exc_info:
            raise BudgetExceededError("max_wall_time_s", 120.0, 125.0)
        assert exc_info.value.limit_type == "max_wall_time_s"


class TestCircuitBreakerOpenError:
    def test_is_langsight_error(self) -> None:
        assert issubclass(CircuitBreakerOpenError, LangSightError)

    def test_stores_attributes(self) -> None:
        err = CircuitBreakerOpenError("postgres-mcp", 42.5)
        assert err.server_name == "postgres-mcp"
        assert err.cooldown_remaining_s == 42.5

    def test_message_contains_details(self) -> None:
        err = CircuitBreakerOpenError("postgres-mcp", 42.5)
        msg = str(err)
        assert "postgres-mcp" in msg
        assert "42.5" in msg

    def test_can_be_raised_and_caught(self) -> None:
        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            raise CircuitBreakerOpenError("s3-mcp", 10.0)
        assert exc_info.value.server_name == "s3-mcp"


# ---------------------------------------------------------------------------
# MCPHealthToolError  (new in recent commit — health probe support)
# ---------------------------------------------------------------------------


class TestMCPHealthToolError:
    """Tests for MCPHealthToolError — MCP layer alive but backend degraded."""

    def test_is_subclass_of_mcp_connection_error(self) -> None:
        """MCPHealthToolError must inherit from MCPConnectionError so callers
        that catch MCPConnectionError keep working after the new subclass lands.
        """
        assert issubclass(MCPHealthToolError, MCPConnectionError)

    def test_is_subclass_of_langsight_error(self) -> None:
        assert issubclass(MCPHealthToolError, LangSightError)

    def test_not_a_timeout_error(self) -> None:
        """MCPHealthToolError is a different failure mode from MCPTimeoutError.
        The two must NOT share a subclass relationship.
        """
        assert not issubclass(MCPHealthToolError, MCPTimeoutError)

    def test_can_be_raised_with_message(self) -> None:
        with pytest.raises(MCPHealthToolError):
            raise MCPHealthToolError("health_tool 'ping' returned error: connection refused")

    def test_message_preserved(self) -> None:
        msg = "health_tool 'ping' not found in tools/list"
        err = MCPHealthToolError(msg)
        assert str(err) == msg

    def test_caught_as_mcp_connection_error(self) -> None:
        """Callers catching the parent class must still intercept it."""
        with pytest.raises(MCPConnectionError):
            raise MCPHealthToolError("backend down")

    def test_caught_as_langsight_error(self) -> None:
        """Top-level LangSightError catch must also intercept it."""
        with pytest.raises(LangSightError):
            raise MCPHealthToolError("backend down")

    def test_not_caught_as_mcp_timeout_error(self) -> None:
        """MCPTimeoutError handler must NOT accidentally catch MCPHealthToolError."""
        raised = MCPHealthToolError("degraded")
        assert not isinstance(raised, MCPTimeoutError)

    def test_can_be_chained_with_cause(self) -> None:
        """Exception chaining (__cause__) must work for 'raise X from Y' patterns."""
        original = ConnectionRefusedError("port 5432 closed")
        with pytest.raises(MCPHealthToolError) as exc_info:
            try:
                raise original
            except ConnectionRefusedError as exc:
                raise MCPHealthToolError("health probe failed") from exc
        assert exc_info.value.__cause__ is original
