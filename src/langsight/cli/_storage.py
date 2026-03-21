"""Shared storage helper for CLI commands.

CLI commands that can run without a database (mcp-health, security-scan,
monitor) use ``try_open_storage()`` instead of ``open_storage()`` directly.
If the database is configured, storage is opened normally. If not, the
command runs stateless — results are displayed but not persisted.

This enables the zero-config first-try experience:
    pip install langsight
    langsight mcp-health      # works immediately, no Docker needed
"""

from __future__ import annotations

import structlog

from langsight.config import LangSightConfig
from langsight.storage.base import StorageBackend

logger = structlog.get_logger()


async def try_open_storage(config: LangSightConfig) -> StorageBackend | None:
    """Try to open the configured storage backend. Return None on failure.

    This is the key enabler for zero-config CLI mode. When no database is
    configured (or unreachable), CLI commands still work — they just don't
    persist results.
    """
    try:
        from langsight.storage.factory import open_storage

        storage = await open_storage(config.storage)
        return storage
    except Exception as exc:  # noqa: BLE001
        logger.debug("cli.storage_unavailable", error=str(exc))
        return None
