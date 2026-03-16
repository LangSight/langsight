"""
Regression tests — full pipeline without real MCP servers.

These tests exercise the complete stack:
  config → HealthChecker → SchemaTracker → SQLiteBackend

Transport (ping) is mocked so no MCP process is needed, but every other
layer is real: real SQLite file, real SchemaTracker logic, real HealthChecker
state machine. If any layer breaks the chain these tests catch it.

Run with: uv run pytest -m regression
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from langsight.config import load_config
from langsight.health.checker import HealthChecker
from langsight.models import ServerStatus, ToolInfo
from langsight.storage.sqlite import SQLiteBackend

pytestmark = pytest.mark.regression

TOOLS_V1 = [
    ToolInfo(name="query", description="Execute SQL"),
    ToolInfo(name="list_tables", description="List tables"),
]
TOOLS_V2 = [
    ToolInfo(name="query", description="Execute SQL"),
    ToolInfo(name="list_tables", description="List tables"),
    ToolInfo(name="new_tool", description="A new tool added in v2"),  # schema change
]


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(yaml.dump({
        "servers": [
            {"name": "pg", "transport": "stdio", "command": "python server.py"},
        ]
    }))
    return cfg


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


class TestHealthPipelineBaseline:
    """First run — no history, baseline stored."""

    async def test_first_run_stores_baseline_and_returns_up(
        self, config_file: Path, db_path: Path
    ) -> None:
        config = load_config(config_file)
        async with await SQLiteBackend.open(db_path) as storage:
            with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
                mock_ping.return_value = (42.0, TOOLS_V1)
                checker = HealthChecker(storage=storage)
                results = await checker.check_many(config.servers)

        assert len(results) == 1
        assert results[0].status == ServerStatus.UP
        assert results[0].tools_count == 2
        assert results[0].schema_hash is not None

    async def test_baseline_persisted_to_sqlite(
        self, config_file: Path, db_path: Path
    ) -> None:
        config = load_config(config_file)
        async with await SQLiteBackend.open(db_path) as storage:
            with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
                mock_ping.return_value = (42.0, TOOLS_V1)
                checker = HealthChecker(storage=storage)
                await checker.check_many(config.servers)
            # Verify within same connection
            stored_hash = await storage.get_latest_schema_hash("pg")

        assert stored_hash is not None
        assert len(stored_hash) == 16


class TestHealthPipelineNoDrift:
    """Second run — same schema, no drift."""

    async def test_second_run_same_schema_returns_up(
        self, config_file: Path, db_path: Path
    ) -> None:
        config = load_config(config_file)

        # Run 1 — store baseline
        async with await SQLiteBackend.open(db_path) as storage:
            with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
                mock_ping.return_value = (42.0, TOOLS_V1)
                await HealthChecker(storage=storage).check_many(config.servers)

        # Run 2 — same tools, different latency
        async with await SQLiteBackend.open(db_path) as storage:
            with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
                mock_ping.return_value = (99.0, TOOLS_V1)
                results = await HealthChecker(storage=storage).check_many(config.servers)

        assert results[0].status == ServerStatus.UP
        assert results[0].error is None

    async def test_history_grows_across_runs(
        self, config_file: Path, db_path: Path
    ) -> None:
        config = load_config(config_file)

        for _ in range(3):
            async with await SQLiteBackend.open(db_path) as storage:
                with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
                    mock_ping.return_value = (10.0, TOOLS_V1)
                    checker = HealthChecker(storage=storage)
                    await checker.check_many(config.servers)

        async with await SQLiteBackend.open(db_path) as storage:
            history = await storage.get_health_history("pg", limit=10)

        assert len(history) == 3
        assert all(r.status == ServerStatus.UP for r in history)


class TestHealthPipelineDriftDetected:
    """Schema drift — tools changed between runs."""

    async def test_drift_sets_degraded_status(
        self, config_file: Path, db_path: Path
    ) -> None:
        config = load_config(config_file)

        # Run 1 — store baseline with TOOLS_V1
        async with await SQLiteBackend.open(db_path) as storage:
            with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
                mock_ping.return_value = (42.0, TOOLS_V1)
                await HealthChecker(storage=storage).check_many(config.servers)

        # Run 2 — TOOLS_V2 (new tool added)
        async with await SQLiteBackend.open(db_path) as storage:
            with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
                mock_ping.return_value = (42.0, TOOLS_V2)
                results = await HealthChecker(storage=storage).check_many(config.servers)

        assert results[0].status == ServerStatus.DEGRADED
        assert results[0].error is not None
        assert "schema drift" in results[0].error

    async def test_drift_error_contains_both_hashes(
        self, config_file: Path, db_path: Path
    ) -> None:
        config = load_config(config_file)

        async with await SQLiteBackend.open(db_path) as storage:
            with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
                mock_ping.return_value = (42.0, TOOLS_V1)
                r1 = await HealthChecker(storage=storage).check_many(config.servers)

        old_hash = r1[0].schema_hash

        async with await SQLiteBackend.open(db_path) as storage:
            with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
                mock_ping.return_value = (42.0, TOOLS_V2)
                r2 = await HealthChecker(storage=storage).check_many(config.servers)

        assert old_hash in r2[0].error  # type: ignore[operator]
        assert r2[0].schema_hash in r2[0].error  # type: ignore[operator]

    async def test_new_snapshot_stored_after_drift(
        self, config_file: Path, db_path: Path
    ) -> None:
        config = load_config(config_file)

        async with await SQLiteBackend.open(db_path) as storage:
            with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
                mock_ping.return_value = (42.0, TOOLS_V1)
                r1 = await HealthChecker(storage=storage).check_many(config.servers)

        async with await SQLiteBackend.open(db_path) as storage:
            with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
                mock_ping.return_value = (42.0, TOOLS_V2)
                r2 = await HealthChecker(storage=storage).check_many(config.servers)

        # Third run — new schema should now be the baseline (no drift)
        async with await SQLiteBackend.open(db_path) as storage:
            with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
                mock_ping.return_value = (42.0, TOOLS_V2)
                r3 = await HealthChecker(storage=storage).check_many(config.servers)

        assert r3[0].status == ServerStatus.UP
        assert r3[0].error is None

    async def test_degraded_result_persisted_to_history(
        self, config_file: Path, db_path: Path
    ) -> None:
        config = load_config(config_file)

        async with await SQLiteBackend.open(db_path) as storage:
            with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
                mock_ping.return_value = (42.0, TOOLS_V1)
                await HealthChecker(storage=storage).check_many(config.servers)

        async with await SQLiteBackend.open(db_path) as storage:
            with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
                mock_ping.return_value = (42.0, TOOLS_V2)
                await HealthChecker(storage=storage).check_many(config.servers)
            history = await storage.get_health_history("pg", limit=10)

        statuses = [r.status for r in history]
        assert ServerStatus.DEGRADED in statuses


class TestHealthPipelineDownServer:
    """Server goes DOWN — result persisted, no crash."""

    async def test_down_result_persisted(
        self, config_file: Path, db_path: Path
    ) -> None:
        from langsight.exceptions import MCPTimeoutError

        config = load_config(config_file)
        async with await SQLiteBackend.open(db_path) as storage:
            with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
                mock_ping.side_effect = MCPTimeoutError("timeout")
                results = await HealthChecker(storage=storage).check_many(config.servers)
            history = await storage.get_health_history("pg")

        assert results[0].status == ServerStatus.DOWN
        assert len(history) == 1
        assert history[0].status == ServerStatus.DOWN

    async def test_recovery_after_down(
        self, config_file: Path, db_path: Path
    ) -> None:
        from langsight.exceptions import MCPTimeoutError

        config = load_config(config_file)

        # Run 1 — DOWN
        async with await SQLiteBackend.open(db_path) as storage:
            with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
                mock_ping.side_effect = MCPTimeoutError("timeout")
                await HealthChecker(storage=storage).check_many(config.servers)

        # Run 2 — recovered
        async with await SQLiteBackend.open(db_path) as storage:
            with patch("langsight.health.checker.ping", new_callable=AsyncMock) as mock_ping:
                mock_ping.return_value = (42.0, TOOLS_V1)
                results = await HealthChecker(storage=storage).check_many(config.servers)

        assert results[0].status == ServerStatus.UP
