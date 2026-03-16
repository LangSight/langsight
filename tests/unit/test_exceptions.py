from __future__ import annotations

import pytest

from langsight.exceptions import (
    ConfigError,
    LangSightError,
    MCPConnectionError,
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
