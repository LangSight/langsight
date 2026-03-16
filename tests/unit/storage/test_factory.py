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
