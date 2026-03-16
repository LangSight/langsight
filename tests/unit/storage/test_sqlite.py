from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from langsight.models import HealthCheckResult, ServerStatus
from langsight.storage.base import StorageBackend
from langsight.storage.sqlite import SQLiteBackend


@pytest.fixture
async def db(tmp_path: Path) -> SQLiteBackend:
    backend = await SQLiteBackend.open(tmp_path / "test.db")
    yield backend
    await backend.close()


UP_RESULT = HealthCheckResult(
    server_name="pg",
    status=ServerStatus.UP,
    latency_ms=42.0,
    tools_count=5,
    schema_hash="abc123def456ab12",
    checked_at=datetime(2026, 3, 16, 12, 0, 0, tzinfo=timezone.utc),
)
DOWN_RESULT = HealthCheckResult(
    server_name="pg",
    status=ServerStatus.DOWN,
    error="timeout after 5s",
    checked_at=datetime(2026, 3, 16, 13, 0, 0, tzinfo=timezone.utc),
)


class TestSQLiteBackendProtocol:
    def test_implements_storage_backend_protocol(self, tmp_path: Path) -> None:
        # SQLiteBackend must satisfy the StorageBackend Protocol structurally
        assert issubclass(SQLiteBackend, StorageBackend)


class TestSQLiteBackendOpen:
    async def test_creates_db_file(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        async with await SQLiteBackend.open(db_path):
            pass
        assert db_path.exists()

    async def test_creates_parent_directories(self, tmp_path: Path) -> None:
        db_path = tmp_path / "nested" / "dirs" / "test.db"
        async with await SQLiteBackend.open(db_path):
            pass
        assert db_path.exists()

    async def test_idempotent_open(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        async with await SQLiteBackend.open(db_path):
            pass
        # Second open should not fail even though tables already exist
        async with await SQLiteBackend.open(db_path):
            pass


class TestSaveHealthResult:
    async def test_saves_up_result(self, db: SQLiteBackend) -> None:
        await db.save_health_result(UP_RESULT)
        history = await db.get_health_history("pg")
        assert len(history) == 1
        assert history[0].status == ServerStatus.UP
        assert history[0].latency_ms == 42.0

    async def test_saves_down_result(self, db: SQLiteBackend) -> None:
        await db.save_health_result(DOWN_RESULT)
        history = await db.get_health_history("pg")
        assert history[0].status == ServerStatus.DOWN
        assert history[0].error == "timeout after 5s"

    async def test_saves_multiple_results(self, db: SQLiteBackend) -> None:
        await db.save_health_result(UP_RESULT)
        await db.save_health_result(DOWN_RESULT)
        history = await db.get_health_history("pg")
        assert len(history) == 2

    async def test_results_ordered_newest_first(self, db: SQLiteBackend) -> None:
        await db.save_health_result(UP_RESULT)    # 12:00
        await db.save_health_result(DOWN_RESULT)  # 13:00
        history = await db.get_health_history("pg")
        assert history[0].status == ServerStatus.DOWN   # newest first
        assert history[1].status == ServerStatus.UP

    async def test_history_isolated_per_server(self, db: SQLiteBackend) -> None:
        other = HealthCheckResult(server_name="s3", status=ServerStatus.UP)
        await db.save_health_result(UP_RESULT)
        await db.save_health_result(other)
        history = await db.get_health_history("pg")
        assert all(r.server_name == "pg" for r in history)

    async def test_history_limit_respected(self, db: SQLiteBackend) -> None:
        for _ in range(5):
            await db.save_health_result(UP_RESULT)
        history = await db.get_health_history("pg", limit=3)
        assert len(history) == 3


class TestSchemaSnapshots:
    async def test_returns_none_when_no_snapshot(self, db: SQLiteBackend) -> None:
        result = await db.get_latest_schema_hash("unknown-server")
        assert result is None

    async def test_returns_stored_hash(self, db: SQLiteBackend) -> None:
        await db.save_schema_snapshot("pg", "abc123", 5)
        result = await db.get_latest_schema_hash("pg")
        assert result == "abc123"

    async def test_returns_most_recent_hash(self, db: SQLiteBackend) -> None:
        await db.save_schema_snapshot("pg", "hash_old", 5)
        await db.save_schema_snapshot("pg", "hash_new", 6)
        result = await db.get_latest_schema_hash("pg")
        assert result == "hash_new"

    async def test_snapshots_isolated_per_server(self, db: SQLiteBackend) -> None:
        await db.save_schema_snapshot("pg", "pg_hash", 5)
        await db.save_schema_snapshot("s3", "s3_hash", 7)
        assert await db.get_latest_schema_hash("pg") == "pg_hash"
        assert await db.get_latest_schema_hash("s3") == "s3_hash"

    async def test_persists_across_connections(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        db1 = await SQLiteBackend.open(db_path)
        await db1.save_schema_snapshot("pg", "persisted_hash", 5)
        await db1.close()

        db2 = await SQLiteBackend.open(db_path)
        result = await db2.get_latest_schema_hash("pg")
        await db2.close()

        assert result == "persisted_hash"
