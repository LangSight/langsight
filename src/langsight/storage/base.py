from __future__ import annotations

from typing import Protocol, runtime_checkable

from langsight.models import HealthCheckResult


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol that all storage backends must implement.

    Implementations: SQLiteBackend (Phase 1), PostgresBackend (Phase 2).
    The rest of the codebase talks only to this interface — never to a
    concrete backend directly. Switching backends is a config change.
    """

    async def save_health_result(self, result: HealthCheckResult) -> None:
        """Persist a health check result."""
        ...

    async def get_latest_schema_hash(self, server_name: str) -> str | None:
        """Return the most recently stored schema hash for a server, or None."""
        ...

    async def save_schema_snapshot(
        self,
        server_name: str,
        schema_hash: str,
        tools_count: int,
    ) -> None:
        """Persist a schema snapshot for drift comparison on the next run."""
        ...

    async def get_health_history(
        self,
        server_name: str,
        limit: int = 10,
    ) -> list[HealthCheckResult]:
        """Return the N most recent health results for a server, newest first."""
        ...

    async def close(self) -> None:
        """Release any resources held by the backend (connections, file handles)."""
        ...
