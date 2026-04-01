"""Integration tests for SchemaTracker against a real storage backend.

These tests use a mock storage backend that fully simulates state transitions
(first-run, no-drift, drift-detected) without requiring a real database.
They verify the complete SchemaTracker.check_and_update() flow including
structural diff and event persistence.

Mark: @pytest.mark.integration
Run: uv run pytest tests/integration/health/test_schema_drift_integration.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call

import pytest

from langsight.health.schema_tracker import SchemaTracker
from langsight.models import DriftType, ToolInfo


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_tool(
    name: str,
    description: str | None = None,
    required: list[str] | None = None,
    properties: dict | None = None,
) -> ToolInfo:
    schema: dict = {}
    if required:
        schema["required"] = required
    if properties:
        schema["properties"] = properties
    return ToolInfo(name=name, description=description, input_schema=schema)


@pytest.fixture
def mock_storage() -> MagicMock:
    """Stateful mock storage that simulates real hash/snapshot storage."""
    storage = MagicMock()
    # Start with no snapshot stored
    storage.get_latest_schema_hash = AsyncMock(return_value=None)
    storage.save_schema_snapshot = AsyncMock()
    storage.upsert_server_tools = AsyncMock()
    storage.get_server_tools = AsyncMock(return_value=[])
    storage.save_schema_drift_event = AsyncMock()
    return storage


@pytest.fixture
def tracker(mock_storage: MagicMock) -> SchemaTracker:
    return SchemaTracker(mock_storage)


# ---------------------------------------------------------------------------
# First-run: baseline stored, no drift
# ---------------------------------------------------------------------------


class TestFirstRunBaseline:
    async def test_first_run_stores_baseline_no_drift(
        self, tracker: SchemaTracker, mock_storage: MagicMock
    ) -> None:
        """On first run (no stored hash), result.drifted is False and baseline is saved."""
        mock_storage.get_latest_schema_hash.return_value = None
        tools = [_make_tool("query_db"), _make_tool("list_tables")]

        result = await tracker.check_and_update(
            server_name="pg",
            current_hash="hash-abc",
            tools_count=2,
            current_tools=tools,
        )

        assert result.drifted is False
        assert result.previous_hash is None
        assert result.current_hash == "hash-abc"
        assert result.changes == []
        assert result.has_breaking is False

    async def test_first_run_saves_snapshot(
        self, tracker: SchemaTracker, mock_storage: MagicMock
    ) -> None:
        """On first run, save_schema_snapshot is called with the correct args."""
        mock_storage.get_latest_schema_hash.return_value = None
        tools = [_make_tool("query_db")]

        await tracker.check_and_update(
            server_name="pg",
            current_hash="initial-hash",
            tools_count=1,
            current_tools=tools,
        )

        mock_storage.save_schema_snapshot.assert_called_once_with("pg", "initial-hash", 1, "")

    async def test_first_run_saves_tool_snapshot(
        self, tracker: SchemaTracker, mock_storage: MagicMock
    ) -> None:
        """On first run with current_tools provided, upsert_server_tools is called."""
        mock_storage.get_latest_schema_hash.return_value = None
        tools = [_make_tool("query_db"), _make_tool("list_tables")]

        await tracker.check_and_update(
            server_name="pg",
            current_hash="initial-hash",
            tools_count=2,
            current_tools=tools,
        )

        mock_storage.upsert_server_tools.assert_called_once()
        tool_dicts = mock_storage.upsert_server_tools.call_args[0][1]
        tool_names = {d["name"] for d in tool_dicts}
        assert tool_names == {"query_db", "list_tables"}


# ---------------------------------------------------------------------------
# Second-run with same hash: no drift
# ---------------------------------------------------------------------------


class TestSecondIdenticalHashNoDrift:
    async def test_second_identical_hash_returns_no_drift(
        self, tracker: SchemaTracker, mock_storage: MagicMock
    ) -> None:
        """When stored hash == current hash, result.drifted is False."""
        mock_storage.get_latest_schema_hash.return_value = "stable-hash"

        result = await tracker.check_and_update(
            server_name="pg",
            current_hash="stable-hash",
            tools_count=3,
            current_tools=None,
        )

        assert result.drifted is False
        assert result.previous_hash == "stable-hash"
        assert result.current_hash == "stable-hash"

    async def test_identical_hash_does_not_save_new_snapshot(
        self, tracker: SchemaTracker, mock_storage: MagicMock
    ) -> None:
        """No-drift run must NOT call save_schema_snapshot."""
        mock_storage.get_latest_schema_hash.return_value = "stable-hash"

        await tracker.check_and_update(
            server_name="pg",
            current_hash="stable-hash",
            tools_count=3,
            current_tools=None,
        )

        mock_storage.save_schema_snapshot.assert_not_called()

    async def test_identical_hash_does_not_persist_drift_event(
        self, tracker: SchemaTracker, mock_storage: MagicMock
    ) -> None:
        """No-drift run must NOT call save_schema_drift_event."""
        mock_storage.get_latest_schema_hash.return_value = "stable-hash"

        await tracker.check_and_update(
            server_name="pg",
            current_hash="stable-hash",
            tools_count=3,
            current_tools=None,
        )

        mock_storage.save_schema_drift_event.assert_not_called()


# ---------------------------------------------------------------------------
# Changed schema: drift with structural diff
# ---------------------------------------------------------------------------


class TestChangedSchemaReturnsDrift:
    async def test_changed_schema_returns_drift_with_changes(
        self, tracker: SchemaTracker, mock_storage: MagicMock
    ) -> None:
        """When hash changes and tools differ, result.drifted is True with changes populated."""
        # Stored tools (old snapshot)
        old_tool_dicts = [
            {"name": "query_db", "description": "Run SQL", "input_schema": '{"required": ["sql"], "properties": {"sql": {"type": "string"}}}'},
        ]
        mock_storage.get_latest_schema_hash.return_value = "old-hash"
        mock_storage.get_server_tools.return_value = old_tool_dicts

        # New tools: query_db now also requires a new param
        new_tools = [
            _make_tool(
                "query_db",
                description="Run SQL",
                required=["sql", "connection_id"],
                properties={"sql": {"type": "string"}, "connection_id": {"type": "string"}},
            )
        ]

        result = await tracker.check_and_update(
            server_name="pg",
            current_hash="new-hash",
            tools_count=1,
            current_tools=new_tools,
        )

        assert result.drifted is True
        assert result.previous_hash == "old-hash"
        assert result.current_hash == "new-hash"
        assert len(result.changes) > 0

    async def test_breaking_change_sets_has_breaking_true(
        self, tracker: SchemaTracker, mock_storage: MagicMock
    ) -> None:
        """A tool_removed change sets has_breaking=True on the result."""
        old_tool_dicts = [
            {"name": "old_tool", "description": None, "input_schema": "{}"},
        ]
        mock_storage.get_latest_schema_hash.return_value = "old-hash"
        mock_storage.get_server_tools.return_value = old_tool_dicts

        # New tools: old_tool is removed — BREAKING
        new_tools: list[ToolInfo] = []

        result = await tracker.check_and_update(
            server_name="pg",
            current_hash="new-hash",
            tools_count=0,
            current_tools=new_tools,
        )

        assert result.has_breaking is True
        assert any(c.drift_type == DriftType.BREAKING for c in result.changes)

    async def test_compatible_change_has_breaking_false(
        self, tracker: SchemaTracker, mock_storage: MagicMock
    ) -> None:
        """A tool_added-only change sets has_breaking=False on the result."""
        old_tool_dicts: list[dict] = []
        mock_storage.get_latest_schema_hash.return_value = "old-hash"
        mock_storage.get_server_tools.return_value = old_tool_dicts

        # New tools: one tool added — COMPATIBLE only
        new_tools = [_make_tool("brand_new_feature")]

        result = await tracker.check_and_update(
            server_name="pg",
            current_hash="new-hash",
            tools_count=1,
            current_tools=new_tools,
        )

        assert result.drifted is True
        assert result.has_breaking is False
        assert all(c.drift_type != DriftType.BREAKING for c in result.changes)

    async def test_drift_detected_saves_new_snapshot(
        self, tracker: SchemaTracker, mock_storage: MagicMock
    ) -> None:
        """On drift, save_schema_snapshot is called with the new hash."""
        mock_storage.get_latest_schema_hash.return_value = "old-hash"
        mock_storage.get_server_tools.return_value = []

        new_tools = [_make_tool("added_tool")]

        await tracker.check_and_update(
            server_name="pg",
            current_hash="new-hash",
            tools_count=1,
            current_tools=new_tools,
        )

        mock_storage.save_schema_snapshot.assert_called_once_with("pg", "new-hash", 1, "")

    async def test_drift_detected_persists_drift_event(
        self, tracker: SchemaTracker, mock_storage: MagicMock
    ) -> None:
        """On drift, save_schema_drift_event is called once with the event."""
        mock_storage.get_latest_schema_hash.return_value = "old-hash"
        mock_storage.get_server_tools.return_value = []

        new_tools = [_make_tool("added_tool")]

        await tracker.check_and_update(
            server_name="pg",
            current_hash="new-hash",
            tools_count=1,
            current_tools=new_tools,
        )

        mock_storage.save_schema_drift_event.assert_called_once()
        event = mock_storage.save_schema_drift_event.call_args[0][0]
        assert event.server_name == "pg"
        assert event.previous_hash == "old-hash"
        assert event.current_hash == "new-hash"

    async def test_drift_updates_tool_snapshot(
        self, tracker: SchemaTracker, mock_storage: MagicMock
    ) -> None:
        """On drift, upsert_server_tools is called with the new tool list."""
        mock_storage.get_latest_schema_hash.return_value = "old-hash"
        mock_storage.get_server_tools.return_value = []

        new_tools = [_make_tool("new_tool_a"), _make_tool("new_tool_b")]

        await tracker.check_and_update(
            server_name="pg",
            current_hash="new-hash",
            tools_count=2,
            current_tools=new_tools,
        )

        mock_storage.upsert_server_tools.assert_called_once()
        tool_names = {d["name"] for d in mock_storage.upsert_server_tools.call_args[0][1]}
        assert tool_names == {"new_tool_a", "new_tool_b"}


# ---------------------------------------------------------------------------
# Drift without current_tools (no structural diff)
# ---------------------------------------------------------------------------


class TestDriftWithoutCurrentTools:
    async def test_drift_without_tools_has_no_changes(
        self, tracker: SchemaTracker, mock_storage: MagicMock
    ) -> None:
        """When current_tools=None, drift is detected but changes list is empty."""
        mock_storage.get_latest_schema_hash.return_value = "old-hash"

        result = await tracker.check_and_update(
            server_name="pg",
            current_hash="new-hash",
            tools_count=5,
            current_tools=None,
        )

        assert result.drifted is True
        assert result.changes == []
        assert result.has_breaking is False
