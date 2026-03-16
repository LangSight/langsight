from __future__ import annotations


class LangSightError(Exception):
    """Base exception for all LangSight errors."""


class MCPConnectionError(LangSightError):
    """Failed to establish a connection to an MCP server."""


class MCPTimeoutError(MCPConnectionError):
    """Connection to an MCP server timed out."""


class MCPProtocolError(LangSightError):
    """Unexpected MCP protocol response — likely a server-side bug."""


class ConfigError(LangSightError):
    """Invalid or missing LangSight configuration."""


class SchemaChangedError(LangSightError):
    """An MCP server's tool schema changed since the last recorded snapshot."""

    def __init__(self, server_name: str, old_hash: str, new_hash: str) -> None:
        self.server_name = server_name
        self.old_hash = old_hash
        self.new_hash = new_hash
        super().__init__(f"Schema changed for '{server_name}': {old_hash} → {new_hash}")
