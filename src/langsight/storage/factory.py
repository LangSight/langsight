from __future__ import annotations

from langsight.config import StorageConfig
from langsight.exceptions import ConfigError
from langsight.storage.base import StorageBackend


async def open_storage(config: StorageConfig) -> StorageBackend:
    """Open the configured storage backend and return it.

    Dispatches based on config.mode:
      - "sqlite"   → SQLiteBackend  (default, zero-dependency local mode)
      - "postgres"  → PostgresBackend (production, requires postgres_url)

    The returned backend is open but not yet inside a context manager.
    Callers should use it as an async context manager:

        async with await open_storage(config) as storage:
            await storage.save_health_result(result)

    Or manage lifecycle manually:

        storage = await open_storage(config)
        try:
            ...
        finally:
            await storage.close()
    """
    mode = config.mode.lower()

    if mode == "sqlite":
        from pathlib import Path

        from langsight.storage.sqlite import SQLiteBackend

        path = Path(config.sqlite_path).expanduser() if config.sqlite_path else None  # noqa: ASYNC240
        return await SQLiteBackend.open(path)

    if mode == "postgres":
        if not config.postgres_url:
            raise ConfigError(
                "storage.mode is 'postgres' but storage.postgres_url is not set. "
                "Add it to .langsight.yaml or set LANGSIGHT_POSTGRES_URL."
            )
        from langsight.storage.postgres import PostgresBackend

        return await PostgresBackend.open(config.postgres_url)

    raise ConfigError(f"Unknown storage mode '{config.mode}'. Valid values: 'sqlite', 'postgres'.")
