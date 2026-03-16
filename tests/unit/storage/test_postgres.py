from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from langsight.models import HealthCheckResult, ServerStatus
from langsight.storage.base import StorageBackend
from langsight.storage.postgres import PostgresBackend, _redact_dsn


def _result(
    name: str = "pg",
    status: ServerStatus = ServerStatus.UP,
) -> HealthCheckResult:
    return HealthCheckResult(
        server_name=name,
        status=status,
        latency_ms=42.0,
        tools_count=5,
        schema_hash="abc123def456ab12",
        checked_at=datetime(2026, 3, 16, 12, 0, 0, tzinfo=UTC),
    )


def _mock_pool() -> MagicMock:
    """Return a mock asyncpg Pool."""
    conn = AsyncMock()
    conn.execute = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])
    conn.transaction = MagicMock()
    conn.transaction.return_value.__aenter__ = AsyncMock(return_value=conn)
    conn.transaction.return_value.__aexit__ = AsyncMock(return_value=None)
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=None)

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=conn)
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    pool.close = AsyncMock()
    return pool


@pytest.fixture
def pool() -> MagicMock:
    return _mock_pool()


@pytest.fixture
def backend(pool: MagicMock) -> PostgresBackend:
    return PostgresBackend(pool)


class TestPostgresBackendProtocol:
    def test_implements_storage_backend_protocol(self) -> None:
        pool = _mock_pool()
        backend = PostgresBackend(pool)
        assert isinstance(backend, StorageBackend)


class TestSaveHealthResult:
    async def test_calls_execute_with_correct_values(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        result = _result()
        await backend.save_health_result(result)
        conn = pool.acquire.return_value.__aenter__.return_value
        conn.execute.assert_called_once()
        args = conn.execute.call_args[0]
        assert "pg" in args
        assert "up" in args
        assert 42.0 in args

    async def test_saves_down_result(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        result = _result(status=ServerStatus.DOWN)
        result = HealthCheckResult(
            server_name="pg",
            status=ServerStatus.DOWN,
            error="timeout",
            checked_at=datetime(2026, 3, 16, 12, 0, 0, tzinfo=UTC),
        )
        await backend.save_health_result(result)
        conn = pool.acquire.return_value.__aenter__.return_value
        conn.execute.assert_called_once()


class TestGetLatestSchemaHash:
    async def test_returns_none_when_no_row(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        pool.acquire.return_value.__aenter__.return_value.fetchrow.return_value = None
        result = await backend.get_latest_schema_hash("pg")
        assert result is None

    async def test_returns_hash_from_row(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        mock_row = {"schema_hash": "abc123def456ab12"}
        pool.acquire.return_value.__aenter__.return_value.fetchrow.return_value = mock_row
        result = await backend.get_latest_schema_hash("pg")
        assert result == "abc123def456ab12"

    async def test_queries_with_server_name(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        await backend.get_latest_schema_hash("my-server")
        conn = pool.acquire.return_value.__aenter__.return_value
        conn.fetchrow.assert_called_once()
        assert "my-server" in conn.fetchrow.call_args[0]


class TestSaveSchemaSnapshot:
    async def test_calls_execute(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        await backend.save_schema_snapshot("pg", "abc123", 5)
        conn = pool.acquire.return_value.__aenter__.return_value
        conn.execute.assert_called_once()
        args = conn.execute.call_args[0]
        assert "pg" in args
        assert "abc123" in args
        assert 5 in args


class TestGetHealthHistory:
    async def test_returns_empty_when_no_rows(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        pool.acquire.return_value.__aenter__.return_value.fetch.return_value = []
        results = await backend.get_health_history("pg")
        assert results == []

    async def test_passes_limit_to_query(
        self, backend: PostgresBackend, pool: MagicMock
    ) -> None:
        await backend.get_health_history("pg", limit=25)
        conn = pool.acquire.return_value.__aenter__.return_value
        conn.fetch.assert_called_once()
        assert 25 in conn.fetch.call_args[0]


class TestRedactDsn:
    def test_redacts_password(self) -> None:
        dsn = "postgresql://user:supersecret@localhost:5432/mydb"
        redacted = _redact_dsn(dsn)
        assert "supersecret" not in redacted
        assert "***" in redacted
        assert "user" in redacted
        assert "localhost" in redacted

    def test_no_password_unchanged(self) -> None:
        dsn = "postgresql://localhost:5432/mydb"
        assert _redact_dsn(dsn) == dsn

    def test_invalid_dsn_returned_as_is(self) -> None:
        dsn = "not-a-valid-dsn"
        result = _redact_dsn(dsn)
        assert result == dsn


class TestContextManager:
    async def test_close_called_on_exit(self, pool: MagicMock) -> None:
        backend = PostgresBackend(pool)
        async with backend:
            pass
        pool.close.assert_called_once()
