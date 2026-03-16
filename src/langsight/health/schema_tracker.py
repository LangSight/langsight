from __future__ import annotations

from dataclasses import dataclass

import structlog

from langsight.storage.base import StorageBackend

logger = structlog.get_logger()


@dataclass(frozen=True)
class SchemaDriftResult:
    """Outcome of a schema drift check for one server."""

    server_name: str
    drifted: bool
    previous_hash: str | None
    current_hash: str


class SchemaTracker:
    """Detects schema drift by comparing current tool hashes against stored snapshots.

    On each health check:
    1. Compute the schema hash from the live tools/list response.
    2. Look up the last stored hash for that server.
    3. If hashes differ → drift detected; update the snapshot.
    4. If no snapshot exists → first run; store the baseline.
    """

    def __init__(self, storage: StorageBackend) -> None:
        self._storage = storage

    async def check_and_update(
        self,
        server_name: str,
        current_hash: str,
        tools_count: int,
    ) -> SchemaDriftResult:
        """Compare current_hash against the stored snapshot and update if needed.

        Returns a SchemaDriftResult indicating whether drift was detected.
        """
        previous_hash = await self._storage.get_latest_schema_hash(server_name)

        if previous_hash is None:
            # First run — store baseline, no drift to report
            await self._storage.save_schema_snapshot(server_name, current_hash, tools_count)
            logger.info(
                "schema_tracker.baseline_stored",
                server=server_name,
                hash=current_hash,
                tools=tools_count,
            )
            return SchemaDriftResult(
                server_name=server_name,
                drifted=False,
                previous_hash=None,
                current_hash=current_hash,
            )

        if previous_hash == current_hash:
            logger.debug("schema_tracker.no_drift", server=server_name, hash=current_hash)
            return SchemaDriftResult(
                server_name=server_name,
                drifted=False,
                previous_hash=previous_hash,
                current_hash=current_hash,
            )

        # Hashes differ — drift detected, update snapshot
        await self._storage.save_schema_snapshot(server_name, current_hash, tools_count)
        logger.warning(
            "schema_tracker.drift_detected",
            server=server_name,
            previous_hash=previous_hash,
            current_hash=current_hash,
        )
        return SchemaDriftResult(
            server_name=server_name,
            drifted=True,
            previous_hash=previous_hash,
            current_hash=current_hash,
        )
