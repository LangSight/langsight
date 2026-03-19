from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from langsight.config import StorageConfig
from langsight.exceptions import ConfigError
from langsight.storage.factory import open_storage
from langsight.storage.sqlite import SQLiteBackend


class TestOpenStorage:
    async def test_opens_sqlite_by_default(self, tmp_path: Path) -> None:
        config = StorageConfig(mode="sqlite", sqlite_path=str(tmp_path / "test.db"))
        storage = await open_storage(config)
        assert isinstance(storage, SQLiteBackend)
        await storage.close()

    async def test_sqlite_mode_explicit(self, tmp_path: Path) -> None:
        config = StorageConfig(mode="sqlite", sqlite_path=str(tmp_path / "test.db"))
        storage = await open_storage(config)
        assert isinstance(storage, SQLiteBackend)
        await storage.close()

    async def test_postgres_mode_without_url_raises_config_error(self) -> None:
        config = StorageConfig(mode="postgres", postgres_url=None)
        with pytest.raises(ConfigError, match="postgres_url"):
            await open_storage(config)

    async def test_postgres_mode_with_url_opens_postgres_backend(self) -> None:
        from langsight.storage.postgres import PostgresBackend

        config = StorageConfig(
            mode="postgres",
            postgres_url="postgresql://user:pass@localhost:5432/test",
        )
        with patch(
            "langsight.storage.postgres.PostgresBackend.open",
            new_callable=AsyncMock,
        ) as mock_open:
            mock_backend = AsyncMock(spec=PostgresBackend)
            mock_open.return_value = mock_backend
            storage = await open_storage(config)

        mock_open.assert_called_once_with(
            "postgresql://user:pass@localhost:5432/test"
        )
        assert storage is mock_backend

    async def test_unknown_mode_raises_config_error(self) -> None:
        config = StorageConfig(mode="redis")  # not a valid mode
        with pytest.raises(ConfigError, match="Unknown storage mode"):
            await open_storage(config)

    async def test_mode_is_case_insensitive(self, tmp_path: Path) -> None:
        config = StorageConfig(mode="SQLite", sqlite_path=str(tmp_path / "test.db"))
        storage = await open_storage(config)
        assert isinstance(storage, SQLiteBackend)
        await storage.close()

    async def test_returned_backend_is_context_manager(self, tmp_path: Path) -> None:
        config = StorageConfig(mode="sqlite", sqlite_path=str(tmp_path / "test.db"))
        async with await open_storage(config) as storage:
            assert storage is not None

    async def test_dual_mode_without_postgres_url_raises_config_error(self) -> None:
        config = StorageConfig(mode="dual", postgres_url=None)
        with pytest.raises(ConfigError, match="postgres_url"):
            await open_storage(config)

    async def test_dual_mode_opens_both_backends_and_returns_dual_storage(self) -> None:
        from langsight.storage.clickhouse import ClickHouseBackend
        from langsight.storage.dual import DualStorage
        from langsight.storage.postgres import PostgresBackend

        config = StorageConfig(
            mode="dual",
            postgres_url="postgresql://user:pass@localhost:5432/test",
            clickhouse_url="http://localhost:8123",
            clickhouse_database="langsight",
        )
        mock_pg = AsyncMock(spec=PostgresBackend)
        mock_ch = AsyncMock(spec=ClickHouseBackend)

        with (
            patch("langsight.storage.postgres.PostgresBackend.open", new_callable=AsyncMock, return_value=mock_pg),
            patch("langsight.storage.clickhouse.ClickHouseBackend.open", new_callable=AsyncMock, return_value=mock_ch),
        ):
            storage = await open_storage(config)

        assert isinstance(storage, DualStorage)
        assert storage._meta is mock_pg
        assert storage._analytics is mock_ch

    async def test_unknown_mode_includes_dual_in_error(self) -> None:
        config = StorageConfig(mode="cassandra")
        with pytest.raises(ConfigError, match="dual"):
            await open_storage(config)
