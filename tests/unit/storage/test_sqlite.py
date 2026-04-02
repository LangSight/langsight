"""Unit tests for SQLiteBackend — uses tmp_path, no Docker required.

Coverage targets:
  - open() creates DB file and all three tables + indexes
  - save_health_result / get_health_history round-trip
  - get_health_history returns newest-first and respects limit
  - get_health_history returns empty list for unknown server
  - get_latest_schema_hash returns None when no snapshot exists
  - save_schema_snapshot upserts (second write replaces, no duplicate row)
  - save_schema_drift_event / get_schema_drift_history round-trip
  - get_schema_drift_history newest-first ordering
  - save_schema_drift_event with empty changes list (no-op, no error)
  - get_distinct_health_server_names returns actual server names
  - All stub methods return correct empty/default values without raising
  - Context manager (__aenter__ / __aexit__) closes the connection
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from langsight.models import (
    DriftType,
    HealthCheckResult,
    SchemaChange,
    SchemaDriftEvent,
    ServerStatus,
)
from langsight.storage.sqlite import DEFAULT_DB_PATH, SQLiteBackend

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _health_result(
    name: str = "my-server",
    status: ServerStatus = ServerStatus.UP,
    latency_ms: float | None = 42.0,
    tools_count: int = 3,
    schema_hash: str | None = "deadbeef01234567",
    checked_at: datetime | None = None,
    error: str | None = None,
) -> HealthCheckResult:
    return HealthCheckResult(
        server_name=name,
        status=status,
        latency_ms=latency_ms,
        tools_count=tools_count,
        schema_hash=schema_hash,
        checked_at=checked_at or datetime.now(UTC),
        error=error,
    )


def _drift_event(
    server_name: str = "my-server",
    current_hash: str = "newhash01234567",
    previous_hash: str | None = "oldhash01234567",
    has_breaking: bool = False,
) -> SchemaDriftEvent:
    return SchemaDriftEvent(
        server_name=server_name,
        changes=[
            SchemaChange(
                drift_type=DriftType.COMPATIBLE,
                kind="tool_added",
                tool_name="new_tool",
                param_name=None,
                old_value=None,
                new_value="new_tool",
            )
        ],
        has_breaking=has_breaking,
        previous_hash=previous_hash,
        current_hash=current_hash,
        detected_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def backend(tmp_path: Path) -> SQLiteBackend:
    """Open a fresh SQLiteBackend in a temp directory."""
    db_path = tmp_path / "test_scan.db"
    b = await SQLiteBackend.open(db_path)
    yield b
    await b.close()


# ---------------------------------------------------------------------------
# open() — schema creation
# ---------------------------------------------------------------------------

class TestOpen:
    async def test_creates_db_file(self, tmp_path: Path) -> None:
        db_path = tmp_path / "new.db"
        assert not db_path.exists()
        b = await SQLiteBackend.open(db_path)
        await b.close()
        assert db_path.exists()

    async def test_creates_parent_directories(self, tmp_path: Path) -> None:
        db_path = tmp_path / "subdir" / "deep" / "scan.db"
        b = await SQLiteBackend.open(db_path)
        await b.close()
        assert db_path.exists()

    async def test_health_results_table_exists(self, tmp_path: Path) -> None:
        db_path = tmp_path / "schema.db"
        import aiosqlite
        b = await SQLiteBackend.open(db_path)
        await b.close()
        async with aiosqlite.connect(str(db_path)) as db:
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='health_results'"
            ) as cursor:
                row = await cursor.fetchone()
        assert row is not None, "health_results table must exist after open()"

    async def test_schema_snapshots_table_exists(self, tmp_path: Path) -> None:
        db_path = tmp_path / "schema.db"
        import aiosqlite
        b = await SQLiteBackend.open(db_path)
        await b.close()
        async with aiosqlite.connect(str(db_path)) as db:
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_snapshots'"
            ) as cursor:
                row = await cursor.fetchone()
        assert row is not None, "schema_snapshots table must exist after open()"

    async def test_schema_drift_events_table_exists(self, tmp_path: Path) -> None:
        db_path = tmp_path / "schema.db"
        import aiosqlite
        b = await SQLiteBackend.open(db_path)
        await b.close()
        async with aiosqlite.connect(str(db_path)) as db:
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_drift_events'"
            ) as cursor:
                row = await cursor.fetchone()
        assert row is not None, "schema_drift_events table must exist after open()"

    async def test_open_twice_does_not_raise(self, tmp_path: Path) -> None:
        """open() is idempotent — calling it on an existing file must not raise."""
        db_path = tmp_path / "idempotent.db"
        b1 = await SQLiteBackend.open(db_path)
        await b1.close()
        b2 = await SQLiteBackend.open(db_path)
        await b2.close()

    async def test_wal_journal_mode_enabled(self, tmp_path: Path) -> None:
        """open() must configure WAL journal mode for concurrent-write safety."""
        import aiosqlite
        db_path = tmp_path / "wal.db"
        b = await SQLiteBackend.open(db_path)
        await b.close()
        async with aiosqlite.connect(str(db_path)) as db:
            async with db.execute("PRAGMA journal_mode") as cursor:
                row = await cursor.fetchone()
        assert row is not None
        assert row[0].lower() == "wal"

    async def test_busy_timeout_set(self, tmp_path: Path) -> None:
        """open() must set a non-zero busy_timeout to allow write retries."""
        db_path = tmp_path / "busy.db"
        b = await SQLiteBackend.open(db_path)
        # Verify via the live connection — busy_timeout is a session pragma
        async with b._db.execute("PRAGMA busy_timeout") as cursor:
            row = await cursor.fetchone()
        await b.close()
        assert row is not None
        assert int(row[0]) >= 1000  # at least 1 second

    async def test_concurrent_writes_do_not_raise(self, tmp_path: Path) -> None:
        """Multiple concurrent coroutines writing health results must not raise 'database is locked'."""
        import asyncio
        from datetime import UTC, datetime
        db_path = tmp_path / "concurrent.db"
        b = await SQLiteBackend.open(db_path)
        try:
            results = [
                HealthCheckResult(
                    server_name=f"srv-{i}",
                    status=ServerStatus.UP,
                    latency_ms=float(i * 10),
                    checked_at=datetime.now(UTC),
                )
                for i in range(10)
            ]
            # Fire all 10 writes concurrently — must not deadlock or raise "database is locked"
            await asyncio.gather(*[b.save_health_result(r) for r in results])

            # Verify all writes landed
            all_names = await b.get_distinct_health_server_names()
            assert len(all_names) == 10
        finally:
            await b.close()


# ---------------------------------------------------------------------------
# save_health_result / get_health_history
# ---------------------------------------------------------------------------

class TestHealthHistory:
    async def test_round_trip_up_result(self, backend: SQLiteBackend) -> None:
        result = _health_result(name="srv-a", status=ServerStatus.UP, latency_ms=55.5)
        await backend.save_health_result(result)
        rows = await backend.get_health_history("srv-a")
        assert len(rows) == 1
        assert rows[0].server_name == "srv-a"
        assert rows[0].status == ServerStatus.UP
        assert rows[0].latency_ms == pytest.approx(55.5)

    async def test_round_trip_down_result_with_error(self, backend: SQLiteBackend) -> None:
        result = _health_result(
            name="srv-b",
            status=ServerStatus.DOWN,
            latency_ms=None,
            error="connection refused",
        )
        await backend.save_health_result(result)
        rows = await backend.get_health_history("srv-b")
        assert rows[0].status == ServerStatus.DOWN
        assert rows[0].error == "connection refused"
        assert rows[0].latency_ms is None

    async def test_round_trip_preserves_tools_count(self, backend: SQLiteBackend) -> None:
        result = _health_result(name="srv-c", tools_count=12)
        await backend.save_health_result(result)
        rows = await backend.get_health_history("srv-c")
        assert rows[0].tools_count == 12

    async def test_round_trip_preserves_schema_hash(self, backend: SQLiteBackend) -> None:
        result = _health_result(name="srv-d", schema_hash="abcd1234ef567890")
        await backend.save_health_result(result)
        rows = await backend.get_health_history("srv-d")
        assert rows[0].schema_hash == "abcd1234ef567890"

    async def test_returns_empty_list_for_unknown_server(self, backend: SQLiteBackend) -> None:
        rows = await backend.get_health_history("no-such-server")
        assert rows == []

    async def test_returns_newest_first(self, backend: SQLiteBackend) -> None:
        """Rows must be ordered by checked_at DESC so newest is first."""
        t1 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
        t2 = datetime(2026, 1, 1, 11, 0, 0, tzinfo=UTC)
        t3 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        await backend.save_health_result(_health_result("ordered", checked_at=t1))
        await backend.save_health_result(_health_result("ordered", checked_at=t3))
        await backend.save_health_result(_health_result("ordered", checked_at=t2))

        rows = await backend.get_health_history("ordered")
        assert rows[0].checked_at >= rows[1].checked_at
        assert rows[1].checked_at >= rows[2].checked_at

    async def test_limit_respected(self, backend: SQLiteBackend) -> None:
        for i in range(5):
            await backend.save_health_result(
                _health_result("limited", checked_at=datetime.now(UTC) + timedelta(seconds=i))
            )
        rows = await backend.get_health_history("limited", limit=3)
        assert len(rows) == 3

    async def test_default_limit_is_10(self, backend: SQLiteBackend) -> None:
        for i in range(15):
            await backend.save_health_result(
                _health_result("big", checked_at=datetime.now(UTC) + timedelta(seconds=i))
            )
        rows = await backend.get_health_history("big")
        assert len(rows) == 10

    async def test_does_not_return_other_servers(self, backend: SQLiteBackend) -> None:
        await backend.save_health_result(_health_result("alpha"))
        await backend.save_health_result(_health_result("beta"))
        rows = await backend.get_health_history("alpha")
        assert all(r.server_name == "alpha" for r in rows)

    async def test_project_id_kwarg_accepted(self, backend: SQLiteBackend) -> None:
        """project_id param is accepted (SQLite ignores it) — must not raise."""
        await backend.save_health_result(_health_result("srv-pi"))
        rows = await backend.get_health_history("srv-pi", project_id="proj-123")
        assert len(rows) == 1

    async def test_all_server_statuses_round_trip(self, backend: SQLiteBackend) -> None:
        for status in ServerStatus:
            await backend.save_health_result(_health_result(f"srv-{status}", status=status))
            rows = await backend.get_health_history(f"srv-{status}")
            assert rows[0].status == status


# ---------------------------------------------------------------------------
# get_latest_schema_hash / save_schema_snapshot
# ---------------------------------------------------------------------------

class TestSchemaSnapshots:
    async def test_returns_none_when_no_snapshot(self, backend: SQLiteBackend) -> None:
        result = await backend.get_latest_schema_hash("unknown-server")
        assert result is None

    async def test_returns_hash_after_save(self, backend: SQLiteBackend) -> None:
        await backend.save_schema_snapshot("srv-snap", "hash_abc123", tools_count=5)
        result = await backend.get_latest_schema_hash("srv-snap")
        assert result == "hash_abc123"

    async def test_upsert_replaces_existing_hash(self, backend: SQLiteBackend) -> None:
        """Second save must update the existing row, not insert a new one."""
        await backend.save_schema_snapshot("srv-upsert", "first_hash_1234", tools_count=2)
        await backend.save_schema_snapshot("srv-upsert", "second_hash_5678", tools_count=4)
        result = await backend.get_latest_schema_hash("srv-upsert")
        assert result == "second_hash_5678"

    async def test_upsert_does_not_duplicate_rows(self, tmp_path: Path) -> None:
        """After two saves for the same server there must be exactly one row."""
        db_path = tmp_path / "nodup.db"
        backend = await SQLiteBackend.open(db_path)
        try:
            await backend.save_schema_snapshot("srv-nodup", "hash_a", tools_count=1)
            await backend.save_schema_snapshot("srv-nodup", "hash_b", tools_count=2)

            # Query through the same connection (backend._db) to avoid reopening
            async with backend._db.execute(
                "SELECT COUNT(*) FROM schema_snapshots WHERE server_name = 'srv-nodup'"
            ) as cursor:
                row = await cursor.fetchone()
        finally:
            await backend.close()
        assert row[0] == 1

    async def test_different_servers_have_independent_snapshots(
        self, backend: SQLiteBackend
    ) -> None:
        await backend.save_schema_snapshot("server-x", "hash_x", tools_count=1)
        await backend.save_schema_snapshot("server-y", "hash_y", tools_count=2)
        assert await backend.get_latest_schema_hash("server-x") == "hash_x"
        assert await backend.get_latest_schema_hash("server-y") == "hash_y"

    async def test_zero_tools_count_saved_correctly(self, backend: SQLiteBackend) -> None:
        await backend.save_schema_snapshot("srv-zero", "hash_zero", tools_count=0)
        result = await backend.get_latest_schema_hash("srv-zero")
        assert result == "hash_zero"


# ---------------------------------------------------------------------------
# save_schema_drift_event / get_schema_drift_history
# ---------------------------------------------------------------------------

class TestSchemaDriftHistory:
    async def test_round_trip_single_change(self, backend: SQLiteBackend) -> None:
        event = _drift_event(server_name="drift-srv")
        await backend.save_schema_drift_event(event)
        rows = await backend.get_schema_drift_history("drift-srv")
        assert len(rows) == 1
        assert rows[0]["server_name"] == "drift-srv"
        assert rows[0]["tool_name"] == "new_tool"
        assert rows[0]["drift_type"] == DriftType.COMPATIBLE.value
        assert rows[0]["change_kind"] == "tool_added"

    async def test_preserves_previous_and_current_hash(self, backend: SQLiteBackend) -> None:
        event = _drift_event(
            server_name="hash-srv",
            previous_hash="prev_hash_abcd",
            current_hash="curr_hash_efgh",
        )
        await backend.save_schema_drift_event(event)
        rows = await backend.get_schema_drift_history("hash-srv")
        assert rows[0]["previous_hash"] == "prev_hash_abcd"
        assert rows[0]["current_hash"] == "curr_hash_efgh"

    async def test_preserves_has_breaking_flag(self, backend: SQLiteBackend) -> None:
        event = _drift_event(server_name="breaking-srv", has_breaking=True)
        await backend.save_schema_drift_event(event)
        rows = await backend.get_schema_drift_history("breaking-srv")
        assert rows[0]["has_breaking"] == 1  # stored as INTEGER

    async def test_multiple_changes_in_one_event_each_stored(
        self, backend: SQLiteBackend
    ) -> None:
        event = SchemaDriftEvent(
            server_name="multi-srv",
            changes=[
                SchemaChange(
                    drift_type=DriftType.BREAKING,
                    kind="tool_removed",
                    tool_name="old_tool",
                ),
                SchemaChange(
                    drift_type=DriftType.COMPATIBLE,
                    kind="tool_added",
                    tool_name="new_tool",
                ),
            ],
            has_breaking=True,
            current_hash="abc",
            detected_at=datetime.now(UTC),
        )
        await backend.save_schema_drift_event(event)
        rows = await backend.get_schema_drift_history("multi-srv")
        assert len(rows) == 2
        tool_names = {r["tool_name"] for r in rows}
        assert tool_names == {"old_tool", "new_tool"}

    async def test_empty_changes_list_does_not_raise(self, backend: SQLiteBackend) -> None:
        """No-op when changes=[] — must not raise or write rows."""
        event = SchemaDriftEvent(
            server_name="empty-srv",
            changes=[],
            has_breaking=False,
            current_hash="hash_empty",
            detected_at=datetime.now(UTC),
        )
        await backend.save_schema_drift_event(event)
        rows = await backend.get_schema_drift_history("empty-srv")
        assert rows == []

    async def test_returns_empty_list_for_unknown_server(self, backend: SQLiteBackend) -> None:
        rows = await backend.get_schema_drift_history("no-such-server")
        assert rows == []

    async def test_returns_newest_first(self, backend: SQLiteBackend) -> None:
        t1 = datetime(2026, 1, 1, 9, 0, 0, tzinfo=UTC)
        t2 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
        event_old = SchemaDriftEvent(
            server_name="order-srv",
            changes=[SchemaChange(drift_type=DriftType.COMPATIBLE, kind="tool_added", tool_name="t1")],
            has_breaking=False,
            current_hash="old_hash",
            detected_at=t1,
        )
        event_new = SchemaDriftEvent(
            server_name="order-srv",
            changes=[SchemaChange(drift_type=DriftType.COMPATIBLE, kind="tool_added", tool_name="t2")],
            has_breaking=False,
            current_hash="new_hash",
            detected_at=t2,
        )
        await backend.save_schema_drift_event(event_old)
        await backend.save_schema_drift_event(event_new)
        rows = await backend.get_schema_drift_history("order-srv")
        assert rows[0]["current_hash"] == "new_hash"
        assert rows[1]["current_hash"] == "old_hash"

    async def test_limit_respected(self, backend: SQLiteBackend) -> None:
        for i in range(5):
            event = SchemaDriftEvent(
                server_name="limit-srv",
                changes=[SchemaChange(drift_type=DriftType.COMPATIBLE, kind="tool_added", tool_name=f"t{i}")],
                has_breaking=False,
                current_hash=f"hash_{i}",
                detected_at=datetime.now(UTC) + timedelta(seconds=i),
            )
            await backend.save_schema_drift_event(event)
        rows = await backend.get_schema_drift_history("limit-srv", limit=3)
        assert len(rows) == 3

    async def test_does_not_return_other_servers(self, backend: SQLiteBackend) -> None:
        await backend.save_schema_drift_event(_drift_event("alpha-drift"))
        await backend.save_schema_drift_event(_drift_event("beta-drift"))
        rows = await backend.get_schema_drift_history("alpha-drift")
        assert all(r["server_name"] == "alpha-drift" for r in rows)

    async def test_row_is_dict_with_expected_keys(self, backend: SQLiteBackend) -> None:
        await backend.save_schema_drift_event(_drift_event("keys-srv"))
        rows = await backend.get_schema_drift_history("keys-srv")
        expected_keys = {
            "server_name", "tool_name", "drift_type", "change_kind", "param_name",
            "old_value", "new_value", "previous_hash", "current_hash",
            "has_breaking", "detected_at",
        }
        assert set(rows[0].keys()) == expected_keys

    async def test_null_previous_hash_stored_and_retrieved(self, backend: SQLiteBackend) -> None:
        event = _drift_event(server_name="null-prev", previous_hash=None)
        await backend.save_schema_drift_event(event)
        rows = await backend.get_schema_drift_history("null-prev")
        assert rows[0]["previous_hash"] is None

    async def test_param_name_preserved(self, backend: SQLiteBackend) -> None:
        event = SchemaDriftEvent(
            server_name="param-srv",
            changes=[
                SchemaChange(
                    drift_type=DriftType.BREAKING,
                    kind="required_param_removed",
                    tool_name="my_tool",
                    param_name="query",
                    old_value="string",
                    new_value=None,
                )
            ],
            has_breaking=True,
            current_hash="hash_param",
            detected_at=datetime.now(UTC),
        )
        await backend.save_schema_drift_event(event)
        rows = await backend.get_schema_drift_history("param-srv")
        assert rows[0]["param_name"] == "query"
        assert rows[0]["old_value"] == "string"
        assert rows[0]["new_value"] is None


# ---------------------------------------------------------------------------
# get_distinct_health_server_names
# ---------------------------------------------------------------------------

class TestGetDistinctHealthServerNames:
    async def test_returns_empty_set_when_no_data(self, backend: SQLiteBackend) -> None:
        names = await backend.get_distinct_health_server_names()
        assert names == set()

    async def test_returns_server_names_after_saves(self, backend: SQLiteBackend) -> None:
        await backend.save_health_result(_health_result("srv-alpha"))
        await backend.save_health_result(_health_result("srv-beta"))
        await backend.save_health_result(_health_result("srv-alpha"))  # duplicate name
        names = await backend.get_distinct_health_server_names()
        assert names == {"srv-alpha", "srv-beta"}

    async def test_project_id_kwarg_accepted(self, backend: SQLiteBackend) -> None:
        """project_id is accepted (SQLite ignores it) — must not raise."""
        await backend.save_health_result(_health_result("srv-scoped"))
        names = await backend.get_distinct_health_server_names(project_id="proj-abc")
        assert "srv-scoped" in names


# ---------------------------------------------------------------------------
# Stubs — return safe empty defaults without raising
# ---------------------------------------------------------------------------

class TestStubs:
    async def test_upsert_server_tools_does_not_raise(self, backend: SQLiteBackend) -> None:
        await backend.upsert_server_tools("srv", [{"name": "t"}])

    async def test_get_server_tools_returns_empty_list(self, backend: SQLiteBackend) -> None:
        result = await backend.get_server_tools("srv")
        assert result == []

    async def test_get_drift_impact_returns_empty_list(self, backend: SQLiteBackend) -> None:
        result = await backend.get_drift_impact("srv", "tool")
        assert result == []

    async def test_create_api_key_does_not_raise(self, backend: SQLiteBackend) -> None:
        await backend.create_api_key(object())

    async def test_list_api_keys_returns_empty_list(self, backend: SQLiteBackend) -> None:
        assert await backend.list_api_keys() == []

    async def test_get_api_key_by_hash_returns_none(self, backend: SQLiteBackend) -> None:
        assert await backend.get_api_key_by_hash("some_hash") is None

    async def test_revoke_api_key_returns_false(self, backend: SQLiteBackend) -> None:
        assert await backend.revoke_api_key("key-id") is False

    async def test_touch_api_key_does_not_raise(self, backend: SQLiteBackend) -> None:
        await backend.touch_api_key("key-id")

    async def test_list_model_pricing_returns_empty_list(self, backend: SQLiteBackend) -> None:
        assert await backend.list_model_pricing() == []

    async def test_get_active_model_pricing_returns_none(self, backend: SQLiteBackend) -> None:
        assert await backend.get_active_model_pricing("gpt-4o") is None

    async def test_create_model_pricing_does_not_raise(self, backend: SQLiteBackend) -> None:
        await backend.create_model_pricing(object())

    async def test_deactivate_model_pricing_returns_false(self, backend: SQLiteBackend) -> None:
        assert await backend.deactivate_model_pricing("entry-id") is False

    async def test_create_project_does_not_raise(self, backend: SQLiteBackend) -> None:
        await backend.create_project(object())

    async def test_get_project_returns_none(self, backend: SQLiteBackend) -> None:
        assert await backend.get_project("project-id") is None

    async def test_get_project_by_slug_returns_none(self, backend: SQLiteBackend) -> None:
        assert await backend.get_project_by_slug("my-slug") is None

    async def test_list_projects_returns_empty_list(self, backend: SQLiteBackend) -> None:
        assert await backend.list_projects() == []

    async def test_list_projects_for_user_returns_empty_list(self, backend: SQLiteBackend) -> None:
        assert await backend.list_projects_for_user("user-id") == []

    async def test_update_project_returns_false(self, backend: SQLiteBackend) -> None:
        assert await backend.update_project("pid", "Name", "slug") is False

    async def test_delete_project_returns_false(self, backend: SQLiteBackend) -> None:
        assert await backend.delete_project("pid") is False

    async def test_add_member_does_not_raise(self, backend: SQLiteBackend) -> None:
        await backend.add_member(object())

    async def test_get_member_returns_none(self, backend: SQLiteBackend) -> None:
        assert await backend.get_member("project-id", "user-id") is None

    async def test_list_members_returns_empty_list(self, backend: SQLiteBackend) -> None:
        assert await backend.list_members("project-id") == []

    async def test_update_member_role_returns_false(self, backend: SQLiteBackend) -> None:
        assert await backend.update_member_role("pid", "uid", "viewer") is False

    async def test_remove_member_returns_false(self, backend: SQLiteBackend) -> None:
        assert await backend.remove_member("pid", "uid") is False

    async def test_create_user_does_not_raise(self, backend: SQLiteBackend) -> None:
        await backend.create_user(object())

    async def test_get_user_by_email_returns_none(self, backend: SQLiteBackend) -> None:
        assert await backend.get_user_by_email("user@example.com") is None

    async def test_get_user_by_id_returns_none(self, backend: SQLiteBackend) -> None:
        assert await backend.get_user_by_id("user-id") is None

    async def test_list_users_returns_empty_list(self, backend: SQLiteBackend) -> None:
        assert await backend.list_users() == []

    async def test_update_user_role_returns_false(self, backend: SQLiteBackend) -> None:
        assert await backend.update_user_role("uid", "admin") is False

    async def test_deactivate_user_returns_false(self, backend: SQLiteBackend) -> None:
        assert await backend.deactivate_user("uid") is False

    async def test_touch_user_login_does_not_raise(self, backend: SQLiteBackend) -> None:
        await backend.touch_user_login("uid")

    async def test_count_users_returns_zero(self, backend: SQLiteBackend) -> None:
        assert await backend.count_users() == 0

    async def test_create_invite_does_not_raise(self, backend: SQLiteBackend) -> None:
        await backend.create_invite(object())

    async def test_get_invite_returns_none(self, backend: SQLiteBackend) -> None:
        assert await backend.get_invite("token") is None

    async def test_mark_invite_used_does_not_raise(self, backend: SQLiteBackend) -> None:
        await backend.mark_invite_used("token")

    async def test_accept_invite_returns_false(self, backend: SQLiteBackend) -> None:
        assert await backend.accept_invite("token", object()) is False

    async def test_create_slo_does_not_raise(self, backend: SQLiteBackend) -> None:
        await backend.create_slo(object())

    async def test_list_slos_returns_empty_list(self, backend: SQLiteBackend) -> None:
        assert await backend.list_slos() == []

    async def test_get_slo_returns_none(self, backend: SQLiteBackend) -> None:
        assert await backend.get_slo("slo-id") is None

    async def test_delete_slo_returns_false(self, backend: SQLiteBackend) -> None:
        assert await backend.delete_slo("slo-id") is False

    async def test_get_alert_config_returns_none(self, backend: SQLiteBackend) -> None:
        assert await backend.get_alert_config() is None

    async def test_save_alert_config_does_not_raise(self, backend: SQLiteBackend) -> None:
        await backend.save_alert_config(None, {})

    async def test_append_audit_log_does_not_raise(self, backend: SQLiteBackend) -> None:
        await backend.append_audit_log("event", "uid", "127.0.0.1", {})

    async def test_list_audit_logs_returns_empty_list(self, backend: SQLiteBackend) -> None:
        assert await backend.list_audit_logs() == []

    async def test_count_audit_logs_returns_zero(self, backend: SQLiteBackend) -> None:
        assert await backend.count_audit_logs() == 0

    async def test_get_all_agent_metadata_returns_empty_list(self, backend: SQLiteBackend) -> None:
        assert await backend.get_all_agent_metadata() == []

    async def test_get_agent_metadata_returns_none(self, backend: SQLiteBackend) -> None:
        assert await backend.get_agent_metadata("agent-name") is None

    async def test_upsert_agent_metadata_returns_empty_dict(self, backend: SQLiteBackend) -> None:
        result = await backend.upsert_agent_metadata(
            "agent-name", "desc", "owner@example.com", [], "active", ""
        )
        assert result == {}

    async def test_delete_agent_metadata_returns_false(self, backend: SQLiteBackend) -> None:
        assert await backend.delete_agent_metadata("agent-name") is False

    async def test_get_all_server_metadata_returns_empty_list(self, backend: SQLiteBackend) -> None:
        assert await backend.get_all_server_metadata() == []

    async def test_get_server_metadata_returns_none(self, backend: SQLiteBackend) -> None:
        assert await backend.get_server_metadata("srv") is None

    async def test_upsert_server_metadata_returns_empty_dict(self, backend: SQLiteBackend) -> None:
        result = await backend.upsert_server_metadata(server_name="srv")
        assert result == {}

    async def test_delete_server_metadata_returns_false(self, backend: SQLiteBackend) -> None:
        assert await backend.delete_server_metadata("srv") is False

    async def test_list_prevention_configs_returns_empty_list(self, backend: SQLiteBackend) -> None:
        assert await backend.list_prevention_configs("project-id") == []

    async def test_get_prevention_config_returns_none(self, backend: SQLiteBackend) -> None:
        assert await backend.get_prevention_config("agent-name", "project-id") is None

    async def test_get_effective_prevention_config_returns_none(self, backend: SQLiteBackend) -> None:
        assert await backend.get_effective_prevention_config("agent-name", "project-id") is None

    async def test_upsert_prevention_config_returns_config(self, backend: SQLiteBackend) -> None:
        sentinel = object()
        result = await backend.upsert_prevention_config(sentinel)
        assert result is sentinel

    async def test_delete_prevention_config_returns_false(self, backend: SQLiteBackend) -> None:
        assert await backend.delete_prevention_config("agent-name", "project-id") is False

    async def test_save_session_health_tag_does_not_raise(self, backend: SQLiteBackend) -> None:
        await backend.save_session_health_tag("session-id", "healthy")

    async def test_get_session_health_tag_returns_none(self, backend: SQLiteBackend) -> None:
        assert await backend.get_session_health_tag("session-id") is None

    async def test_get_untagged_sessions_returns_empty_list(self, backend: SQLiteBackend) -> None:
        assert await backend.get_untagged_sessions() == []


# ---------------------------------------------------------------------------
# Lifecycle — context manager + close
# ---------------------------------------------------------------------------

class TestLifecycle:
    async def test_close_does_not_raise(self, tmp_path: Path) -> None:
        db_path = tmp_path / "close_test.db"
        b = await SQLiteBackend.open(db_path)
        await b.close()  # must not raise

    async def test_context_manager_closes_connection(self, tmp_path: Path) -> None:
        db_path = tmp_path / "ctx.db"
        async with await SQLiteBackend.open(db_path) as backend:
            await backend.save_health_result(_health_result("ctx-srv"))
        # After __aexit__ the connection is closed; accessing it should fail
        with pytest.raises(Exception):
            await backend.save_health_result(_health_result("ctx-srv-2"))

    async def test_context_manager_returns_same_backend(self, tmp_path: Path) -> None:
        db_path = tmp_path / "ctx2.db"
        b = await SQLiteBackend.open(db_path)
        async with b as entered:
            assert entered is b
        # b is closed now; no need to close again


# ---------------------------------------------------------------------------
# DEFAULT_DB_PATH sanity check
# ---------------------------------------------------------------------------

class TestDefaultDbPath:
    def test_default_db_path_is_under_home(self) -> None:
        assert str(DEFAULT_DB_PATH).endswith("scan.db")
        assert ".langsight" in str(DEFAULT_DB_PATH)
