from __future__ import annotations

from langsight.config import StorageConfig
from langsight.exceptions import ConfigError
from langsight.storage.base import StorageBackend


async def open_storage(config: StorageConfig) -> StorageBackend:
    """Open the configured storage backend and return it.

    Dispatches based on config.mode:
      - "postgres"    → PostgresBackend  (metadata only — users, projects, API keys, SLOs)
      - "clickhouse"  → ClickHouseBackend (analytics only — spans, health, costs)
      - "dual"        → DualStorage (Postgres metadata + ClickHouse analytics) — production default

    The returned backend is open but not yet inside a context manager.
    Callers should use it as an async context manager:

        async with await open_storage(config) as storage:
            await storage.save_health_result(result)
    """
    mode = config.mode.lower()

    if mode == "postgres":
        if not config.postgres_url:
            raise ConfigError(
                "storage.mode is 'postgres' but storage.postgres_url is not set. "
                "Add it to .langsight.yaml or set LANGSIGHT_POSTGRES_URL."
            )
        from langsight.storage.postgres import PostgresBackend

        return await PostgresBackend.open(
            config.postgres_url, min_size=config.pg_pool_min, max_size=config.pg_pool_max
        )

    if mode == "clickhouse":
        from urllib.parse import urlparse

        from langsight.storage.clickhouse import ClickHouseBackend

        parsed = urlparse(config.clickhouse_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 8123
        return await ClickHouseBackend.open(  # type: ignore[return-value]
            host=host,
            port=port,
            database=config.clickhouse_database,
            username=config.clickhouse_username,
            password=config.clickhouse_password,
        )

    if mode == "dual":
        if not config.postgres_url:
            raise ConfigError(
                "storage.mode is 'dual' but storage.postgres_url is not set. "
                "Set LANGSIGHT_POSTGRES_URL or add postgres_url to .langsight.yaml."
            )
        from urllib.parse import urlparse

        from langsight.storage.clickhouse import ClickHouseBackend
        from langsight.storage.dual import DualStorage
        from langsight.storage.postgres import PostgresBackend

        parsed = urlparse(config.clickhouse_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 8123
        metadata = await PostgresBackend.open(
            config.postgres_url, min_size=config.pg_pool_min, max_size=config.pg_pool_max
        )
        analytics = await ClickHouseBackend.open(
            host=host,
            port=port,
            database=config.clickhouse_database,
            username=config.clickhouse_username,
            password=config.clickhouse_password,
        )
        return DualStorage(metadata, analytics)

    if mode == "sqlite":
        from pathlib import Path

        from langsight.storage.sqlite import DEFAULT_DB_PATH, SQLiteBackend

        _sqlite_path = getattr(config, "sqlite_path", None)
        db_path = Path(_sqlite_path) if _sqlite_path else DEFAULT_DB_PATH
        return await SQLiteBackend.open(db_path)

    raise ConfigError(
        f"Unknown storage mode '{config.mode}'. "
        "Valid values: 'postgres', 'clickhouse', 'dual', 'sqlite'."
    )
