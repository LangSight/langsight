from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from langsight.health.schema_tracker import SchemaTracker
from langsight.storage.base import StorageBackend


@pytest.fixture
def mock_storage() -> MagicMock:
    storage = MagicMock(spec=StorageBackend)
    storage.get_latest_schema_hash = AsyncMock(return_value=None)
    storage.save_schema_snapshot = AsyncMock()
    return storage


@pytest.fixture
def tracker(mock_storage: MagicMock) -> SchemaTracker:
    return SchemaTracker(mock_storage)


class TestSchemaTrackerFirstRun:
    async def test_no_drift_on_first_run(
        self, tracker: SchemaTracker, mock_storage: MagicMock
    ) -> None:
        mock_storage.get_latest_schema_hash.return_value = None
        result = await tracker.check_and_update("pg", "abc123", 5)
        assert result.drifted is False

    async def test_stores_baseline_on_first_run(
        self, tracker: SchemaTracker, mock_storage: MagicMock
    ) -> None:
        mock_storage.get_latest_schema_hash.return_value = None
        await tracker.check_and_update("pg", "abc123", 5)
        mock_storage.save_schema_snapshot.assert_called_once_with("pg", "abc123", 5, "")

    async def test_previous_hash_is_none_on_first_run(
        self, tracker: SchemaTracker, mock_storage: MagicMock
    ) -> None:
        mock_storage.get_latest_schema_hash.return_value = None
        result = await tracker.check_and_update("pg", "abc123", 5)
        assert result.previous_hash is None
        assert result.current_hash == "abc123"


class TestSchemaTrackerNoDrift:
    async def test_no_drift_when_hashes_match(
        self, tracker: SchemaTracker, mock_storage: MagicMock
    ) -> None:
        mock_storage.get_latest_schema_hash.return_value = "abc123"
        result = await tracker.check_and_update("pg", "abc123", 5)
        assert result.drifted is False

    async def test_does_not_save_snapshot_when_no_drift(
        self, tracker: SchemaTracker, mock_storage: MagicMock
    ) -> None:
        mock_storage.get_latest_schema_hash.return_value = "abc123"
        await tracker.check_and_update("pg", "abc123", 5)
        mock_storage.save_schema_snapshot.assert_not_called()

    async def test_returns_correct_hashes_when_no_drift(
        self, tracker: SchemaTracker, mock_storage: MagicMock
    ) -> None:
        mock_storage.get_latest_schema_hash.return_value = "abc123"
        result = await tracker.check_and_update("pg", "abc123", 5)
        assert result.previous_hash == "abc123"
        assert result.current_hash == "abc123"


class TestSchemaTrackerDriftDetected:
    async def test_drift_detected_when_hashes_differ(
        self, tracker: SchemaTracker, mock_storage: MagicMock
    ) -> None:
        mock_storage.get_latest_schema_hash.return_value = "old_hash"
        result = await tracker.check_and_update("pg", "new_hash", 6)
        assert result.drifted is True

    async def test_saves_new_snapshot_on_drift(
        self, tracker: SchemaTracker, mock_storage: MagicMock
    ) -> None:
        mock_storage.get_latest_schema_hash.return_value = "old_hash"
        await tracker.check_and_update("pg", "new_hash", 6)
        mock_storage.save_schema_snapshot.assert_called_once_with("pg", "new_hash", 6, "")

    async def test_returns_both_hashes_on_drift(
        self, tracker: SchemaTracker, mock_storage: MagicMock
    ) -> None:
        mock_storage.get_latest_schema_hash.return_value = "old_hash"
        result = await tracker.check_and_update("pg", "new_hash", 6)
        assert result.previous_hash == "old_hash"
        assert result.current_hash == "new_hash"
        assert result.server_name == "pg"
