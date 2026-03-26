"""Unit tests for langsight.cli.init — transport detection, config parsing,
fingerprinting, deduplication, and platform-aware path generation.

All tests are offline — no real MCP connections, no filesystem side-effects
beyond tmp_path.
"""

from __future__ import annotations

import json
import platform
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from click.testing import CliRunner

from langsight.cli.init import (
    _detect_transport,
    _discover_servers,
    _fingerprint,
    _get_config_sources,
    _parse_mcp_config,
)
from langsight.cli.main import cli


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_config(path: Path, content: dict) -> Path:
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# _detect_transport
# ---------------------------------------------------------------------------


class TestDetectTransport:
    def test_detect_transport_stdio(self) -> None:
        """A server entry with 'command' key → stdio transport."""
        cfg = {"command": "uv", "args": ["run", "server.py"]}
        assert _detect_transport(cfg) == "stdio"

    def test_detect_transport_sse(self) -> None:
        """URL whose last path segment is exactly 'sse' → sse transport."""
        cfg = {"url": "http://localhost:8080/sse"}
        assert _detect_transport(cfg) == "sse"

    def test_detect_transport_sse_trailing_slash(self) -> None:
        """URL with trailing slash on /sse still resolves to sse."""
        cfg = {"url": "http://localhost:8080/sse/"}
        assert _detect_transport(cfg) == "sse"

    def test_detect_transport_streamable_http(self) -> None:
        """URL not ending in /sse → streamable_http."""
        cfg = {"url": "https://postgres-mcp.internal.company.com/mcp"}
        assert _detect_transport(cfg) == "streamable_http"

    def test_detect_transport_url_with_sse_in_domain(self) -> None:
        """Regression: 'sse' in domain name must NOT trigger sse transport.

        https://sse-server.com/mcp → last path segment is 'mcp' not 'sse'
        so transport must be streamable_http.
        """
        cfg = {"url": "https://sse-server.com/mcp"}
        assert _detect_transport(cfg) == "streamable_http"

    def test_detect_transport_url_with_sse_in_subdirectory(self) -> None:
        """Path /sse/health → last segment is 'health', not sse → streamable_http."""
        cfg = {"url": "http://localhost:9000/sse/health"}
        assert _detect_transport(cfg) == "streamable_http"

    def test_detect_transport_no_url_no_command(self) -> None:
        """Empty config entry with no command or url falls back to stdio."""
        cfg: dict = {}
        assert _detect_transport(cfg) == "stdio"

    def test_detect_transport_command_takes_precedence_over_url(self) -> None:
        """When both 'command' and 'url' present, stdio takes precedence."""
        cfg = {"command": "python", "url": "http://localhost:8080/sse"}
        assert _detect_transport(cfg) == "stdio"


# ---------------------------------------------------------------------------
# _parse_mcp_config
# ---------------------------------------------------------------------------


class TestParseMcpConfig:
    def test_parse_mcp_config_mcpservers_key(self, tmp_path: Path) -> None:
        """Standard Claude Desktop / Cursor mcpServers format is parsed correctly."""
        cfg = tmp_path / "claude_desktop_config.json"
        _write_config(cfg, {
            "mcpServers": {
                "postgres": {"command": "python", "args": ["server.py"]}
            }
        })
        servers = _parse_mcp_config(cfg, "Claude Desktop", "mcpServers")
        assert len(servers) == 1
        assert servers[0]["name"] == "postgres"
        assert servers[0]["transport"] == "stdio"
        assert servers[0]["command"] == "python"
        assert servers[0]["args"] == ["server.py"]

    def test_parse_mcp_config_servers_key(self, tmp_path: Path) -> None:
        """VS Code uses 'servers' as the top-level key instead of 'mcpServers'."""
        cfg = tmp_path / "mcp.json"
        _write_config(cfg, {
            "servers": {
                "my-tool": {"url": "http://localhost:8080/mcp"}
            }
        })
        servers = _parse_mcp_config(cfg, "VS Code", "servers")
        assert len(servers) == 1
        assert servers[0]["name"] == "my-tool"
        assert servers[0]["transport"] == "streamable_http"
        assert servers[0]["url"] == "http://localhost:8080/mcp"

    def test_parse_mcp_config_context_servers_key(self, tmp_path: Path) -> None:
        """Zed uses 'context_servers' as the top-level key."""
        cfg = tmp_path / "settings.json"
        _write_config(cfg, {
            "context_servers": {
                "zed-tool": {"url": "http://localhost:7000/sse"}
            }
        })
        servers = _parse_mcp_config(cfg, "Zed", "context_servers")
        assert len(servers) == 1
        assert servers[0]["name"] == "zed-tool"
        assert servers[0]["transport"] == "sse"

    def test_parse_mcp_config_array_format(self, tmp_path: Path) -> None:
        """Continue.dev stores servers as an array — should be normalised to dict."""
        cfg = tmp_path / "config.json"
        _write_config(cfg, {
            "mcpServers": [
                {"name": "arr-server", "command": "npx", "args": ["-y", "server"]},
                {"name": "arr-http", "url": "http://localhost:9000/mcp"},
            ]
        })
        servers = _parse_mcp_config(cfg, "Continue.dev", "mcpServers")
        names = {s["name"] for s in servers}
        assert names == {"arr-server", "arr-http"}
        stdio_entry = next(s for s in servers if s["name"] == "arr-server")
        assert stdio_entry["transport"] == "stdio"

    def test_parse_mcp_config_array_format_skips_entries_without_name(
        self, tmp_path: Path
    ) -> None:
        """Array entries lacking a 'name' field are silently skipped."""
        cfg = tmp_path / "config.json"
        _write_config(cfg, {
            "mcpServers": [
                {"command": "python"},        # no 'name'
                {"name": "good", "command": "node"},
            ]
        })
        servers = _parse_mcp_config(cfg, "Continue.dev", "mcpServers")
        assert len(servers) == 1
        assert servers[0]["name"] == "good"

    def test_parse_ignores_non_dict_entries(self, tmp_path: Path) -> None:
        """Non-dict server entries (strings, ints) are skipped without raising."""
        cfg = tmp_path / "mcp.json"
        _write_config(cfg, {
            "mcpServers": {
                "valid": {"command": "python"},
                "invalid": "this-is-a-string",
                "also-invalid": 42,
            }
        })
        servers = _parse_mcp_config(cfg, "Claude Desktop", "mcpServers")
        assert len(servers) == 1
        assert servers[0]["name"] == "valid"

    def test_parse_preserves_env_vars_as_dict(self, tmp_path: Path) -> None:
        """env values from config are stored as-is (dict), not expanded."""
        cfg = tmp_path / "config.json"
        _write_config(cfg, {
            "mcpServers": {
                "pg": {
                    "command": "python",
                    "env": {"DB_PASSWORD": "${SECRET_PASSWORD}", "HOST": "localhost"},
                }
            }
        })
        servers = _parse_mcp_config(cfg, "Claude Desktop", "mcpServers")
        assert servers[0]["env"]["DB_PASSWORD"] == "${SECRET_PASSWORD}"
        assert servers[0]["env"]["HOST"] == "localhost"

    def test_parse_http_server_includes_headers(self, tmp_path: Path) -> None:
        """HTTP servers with headers have them preserved in the output."""
        cfg = tmp_path / "config.json"
        _write_config(cfg, {
            "mcpServers": {
                "secure-tool": {
                    "url": "https://api.example.com/mcp",
                    "headers": {"Authorization": "Bearer TOKEN"},
                }
            }
        })
        servers = _parse_mcp_config(cfg, "Claude Desktop", "mcpServers")
        assert servers[0]["headers"]["Authorization"] == "Bearer TOKEN"

    def test_parse_empty_config_returns_empty_list(self, tmp_path: Path) -> None:
        """A config file with no mcpServers key returns an empty list."""
        cfg = tmp_path / "config.json"
        _write_config(cfg, {"other_key": {}})
        servers = _parse_mcp_config(cfg, "Claude Desktop", "mcpServers")
        assert servers == []

    def test_parse_missing_key_returns_empty_list(self, tmp_path: Path) -> None:
        """Asking for 'context_servers' on a file that doesn't have it → []."""
        cfg = tmp_path / "config.json"
        _write_config(cfg, {"mcpServers": {"pg": {"command": "python"}}})
        servers = _parse_mcp_config(cfg, "Zed", "context_servers")
        assert servers == []

    def test_parse_source_tag_is_set(self, tmp_path: Path) -> None:
        """The 'source' field in every returned dict matches the source argument."""
        cfg = tmp_path / "config.json"
        _write_config(cfg, {"mcpServers": {"pg": {"command": "python"}}})
        servers = _parse_mcp_config(cfg, "Cursor", "mcpServers")
        assert servers[0]["source"] == "Cursor"


# ---------------------------------------------------------------------------
# _fingerprint
# ---------------------------------------------------------------------------


class TestFingerprint:
    def test_fingerprint_stdio_same_command_and_args(self) -> None:
        """Two stdio servers with identical command+args produce the same fingerprint."""
        s1 = {"transport": "stdio", "command": "uv", "args": ["run", "server.py"]}
        s2 = {"transport": "stdio", "command": "uv", "args": ["run", "server.py"]}
        assert _fingerprint(s1) == _fingerprint(s2)

    def test_fingerprint_stdio_different_args(self) -> None:
        """Different args produce different fingerprints."""
        s1 = {"transport": "stdio", "command": "uv", "args": ["run", "server.py"]}
        s2 = {"transport": "stdio", "command": "uv", "args": ["run", "other.py"]}
        assert _fingerprint(s1) != _fingerprint(s2)

    def test_fingerprint_stdio_different_command(self) -> None:
        """Different commands produce different fingerprints."""
        s1 = {"transport": "stdio", "command": "python", "args": []}
        s2 = {"transport": "stdio", "command": "node", "args": []}
        assert _fingerprint(s1) != _fingerprint(s2)

    def test_fingerprint_http_same_url(self) -> None:
        """Two HTTP servers with the same URL produce the same fingerprint."""
        s1 = {"transport": "streamable_http", "url": "https://mcp.example.com/mcp"}
        s2 = {"transport": "streamable_http", "url": "https://mcp.example.com/mcp"}
        assert _fingerprint(s1) == _fingerprint(s2)

    def test_fingerprint_http_different_url(self) -> None:
        """Different URLs produce different fingerprints."""
        s1 = {"transport": "streamable_http", "url": "https://mcp1.example.com/mcp"}
        s2 = {"transport": "streamable_http", "url": "https://mcp2.example.com/mcp"}
        assert _fingerprint(s1) != _fingerprint(s2)

    def test_fingerprint_does_not_include_env_vars(self) -> None:
        """Fingerprint only uses command+args for stdio, not env vars.

        Two servers with same command/args but different env must deduplicate.
        """
        s1 = {"transport": "stdio", "command": "python", "args": [], "env": {"X": "1"}}
        s2 = {"transport": "stdio", "command": "python", "args": [], "env": {"X": "CHANGED"}}
        assert _fingerprint(s1) == _fingerprint(s2)

    def test_fingerprint_sse_uses_url(self) -> None:
        """SSE transport fingerprint is url-based (same as streamable_http)."""
        s1 = {"transport": "sse", "url": "http://localhost:8080/sse"}
        s2 = {"transport": "sse", "url": "http://localhost:8080/sse"}
        assert _fingerprint(s1) == _fingerprint(s2)

    def test_fingerprint_stdio_starts_with_stdio_prefix(self) -> None:
        """stdio fingerprints have a 'stdio:' prefix for readability."""
        s = {"transport": "stdio", "command": "python", "args": []}
        assert _fingerprint(s).startswith("stdio:")

    def test_fingerprint_http_starts_with_http_prefix(self) -> None:
        """HTTP fingerprints have an 'http:' prefix for readability."""
        s = {"transport": "streamable_http", "url": "https://example.com/mcp"}
        assert _fingerprint(s).startswith("http:")


# ---------------------------------------------------------------------------
# _discover_servers — deduplication
# ---------------------------------------------------------------------------


class TestDiscoverDeduplication:
    def test_discover_deduplication(self, tmp_path: Path) -> None:
        """Same server appearing in two config files → appears only once in output."""
        # Two separate config files both define the same stdio server
        config_a = tmp_path / "config_a.json"
        config_b = tmp_path / "config_b.json"
        _write_config(config_a, {
            "mcpServers": {"pg": {"command": "python", "args": ["server.py"]}}
        })
        _write_config(config_b, {
            "mcpServers": {"pg-copy": {"command": "python", "args": ["server.py"]}}
        })

        fake_sources = [
            ("Source A", config_a, "mcpServers"),
            ("Source B", config_b, "mcpServers"),
        ]
        with patch("langsight.cli.init._get_config_sources", return_value=fake_sources):
            servers = _discover_servers()

        # Both have identical command+args → only one survives dedup
        assert len(servers) == 1

    def test_discover_two_different_servers_both_kept(self, tmp_path: Path) -> None:
        """Different servers (different commands) are both retained."""
        config_a = tmp_path / "config_a.json"
        config_b = tmp_path / "config_b.json"
        _write_config(config_a, {
            "mcpServers": {"pg": {"command": "python", "args": ["pg_server.py"]}}
        })
        _write_config(config_b, {
            "mcpServers": {"s3": {"command": "node", "args": ["s3_server.js"]}}
        })

        fake_sources = [
            ("Source A", config_a, "mcpServers"),
            ("Source B", config_b, "mcpServers"),
        ]
        with patch("langsight.cli.init._get_config_sources", return_value=fake_sources):
            servers = _discover_servers()

        assert len(servers) == 2
        names = {s["name"] for s in servers}
        assert names == {"pg", "s3"}

    def test_discover_skips_missing_files(self, tmp_path: Path) -> None:
        """Non-existent config paths are silently skipped."""
        real_cfg = tmp_path / "real.json"
        _write_config(real_cfg, {"mcpServers": {"ok": {"command": "python"}}})
        fake_sources = [
            ("Real", real_cfg, "mcpServers"),
            ("Missing", tmp_path / "does_not_exist.json", "mcpServers"),
        ]
        with patch("langsight.cli.init._get_config_sources", return_value=fake_sources):
            servers = _discover_servers()
        assert len(servers) == 1

    def test_discover_parse_error_skips_file(self, tmp_path: Path) -> None:
        """A config file with invalid JSON is skipped without crashing."""
        bad_cfg = tmp_path / "bad.json"
        bad_cfg.write_text("NOT VALID JSON", encoding="utf-8")
        good_cfg = tmp_path / "good.json"
        _write_config(good_cfg, {"mcpServers": {"ok": {"command": "python"}}})

        fake_sources = [
            ("Bad", bad_cfg, "mcpServers"),
            ("Good", good_cfg, "mcpServers"),
        ]
        with patch("langsight.cli.init._get_config_sources", return_value=fake_sources):
            servers = _discover_servers()
        assert len(servers) == 1
        assert servers[0]["name"] == "ok"


# ---------------------------------------------------------------------------
# _get_config_sources — platform-aware paths
# ---------------------------------------------------------------------------


class TestGetConfigSources:
    def test_get_config_sources_macos(self) -> None:
        """On Darwin, Claude Desktop path is ~/Library/Application Support/Claude/..."""
        with patch("platform.system", return_value="Darwin"):
            sources = _get_config_sources()

        claude = next(s for s in sources if s[0] == "Claude Desktop")
        assert "Library/Application Support/Claude" in str(claude[1])

    def test_get_config_sources_linux(self) -> None:
        """On Linux, Claude Desktop path is ~/.config/Claude/..."""
        with patch("platform.system", return_value="Linux"):
            sources = _get_config_sources()

        claude = next(s for s in sources if s[0] == "Claude Desktop")
        assert ".config/Claude" in str(claude[1])

    def test_get_config_sources_windows(self) -> None:
        """On Windows, Claude Desktop path uses APPDATA."""
        with patch("platform.system", return_value="Windows"):
            with patch.dict("os.environ", {"APPDATA": "C:\\Users\\test\\AppData\\Roaming"}):
                sources = _get_config_sources()

        claude = next(s for s in sources if s[0] == "Claude Desktop")
        assert "Claude" in str(claude[1])

    def test_get_config_sources_includes_vscode(self) -> None:
        """VS Code is always present in the source list."""
        with patch("platform.system", return_value="Linux"):
            sources = _get_config_sources()
        names = [s[0] for s in sources]
        assert "VS Code" in names

    def test_get_config_sources_vscode_uses_servers_key(self) -> None:
        """VS Code source uses 'servers' key, not 'mcpServers'."""
        with patch("platform.system", return_value="Linux"):
            sources = _get_config_sources()
        vscode = next(s for s in sources if s[0] == "VS Code")
        assert vscode[2] == "servers"

    def test_get_config_sources_zed_uses_context_servers_key(self) -> None:
        """Zed source uses 'context_servers' key."""
        with patch("platform.system", return_value="Linux"):
            sources = _get_config_sources()
        zed = next(s for s in sources if s[0] == "Zed")
        assert zed[2] == "context_servers"

    def test_get_config_sources_claude_desktop_uses_mcpservers_key(self) -> None:
        """Claude Desktop source uses 'mcpServers' key."""
        with patch("platform.system", return_value="Darwin"):
            sources = _get_config_sources()
        claude = next(s for s in sources if s[0] == "Claude Desktop")
        assert claude[2] == "mcpServers"

    def test_get_config_sources_returns_at_least_10_entries(self) -> None:
        """At least 10 IDE/client sources are registered on every platform."""
        for system in ("Darwin", "Linux", "Windows"):
            with patch("platform.system", return_value=system):
                with patch.dict("os.environ", {"APPDATA": "C:\\AppData", "USERPROFILE": "C:\\Users\\test"}):
                    sources = _get_config_sources()
            assert len(sources) >= 10, f"Only {len(sources)} sources on {system}"

    def test_get_config_sources_includes_project_local_configs(self) -> None:
        """Project-local configs (.cursor/mcp.json, .mcp.json, .vscode/mcp.json) are included."""
        with patch("platform.system", return_value="Linux"):
            sources = _get_config_sources()
        names = [s[0] for s in sources]
        assert "Cursor (project)" in names
        assert "Claude Code (project)" in names
        assert "VS Code (project)" in names

    def test_get_config_sources_macos_vscode_path(self) -> None:
        """On macOS, VS Code path is ~/Library/Application Support/Code/User/mcp.json."""
        with patch("platform.system", return_value="Darwin"):
            sources = _get_config_sources()
        vscode = next(s for s in sources if s[0] == "VS Code")
        assert "Library/Application Support/Code" in str(vscode[1])

    def test_get_config_sources_linux_vscode_path(self) -> None:
        """On Linux, VS Code path is ~/.config/Code/User/mcp.json."""
        with patch("platform.system", return_value="Linux"):
            sources = _get_config_sources()
        vscode = next(s for s in sources if s[0] == "VS Code")
        assert ".config/Code" in str(vscode[1])
