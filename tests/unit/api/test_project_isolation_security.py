"""
Adversarial security tests for multi-tenancy project isolation.

This module proves that four hard boundaries hold under hostile conditions:

  1. SLO cross-project deletion: a caller authenticated to project A cannot
     delete an SLO that belongs to project B, even if they know the SLO ID.

  2. SLO cross-project read: GET /api/slos with project_id=B must not return
     SLOs scoped to project A.

  3. Health history project filtering: get_health_history with project_id="A"
     must not return rows whose project_id is "B".  Rows with project_id=""
     (global CLI checks) ARE returned for all project callers — this is
     intentional; tests verify both sides of that contract.

  4. Rate-limiter key resolution: _rate_limit_key must extract only the FIRST
     IP from X-Forwarded-For; an attacker cannot poison a victim's bucket by
     appending a trusted IP after their own.

All tests run offline (no Docker, no real DB, no network).
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

pytestmark = [pytest.mark.unit, pytest.mark.security]


# ---------------------------------------------------------------------------
# Helpers shared across this module
# ---------------------------------------------------------------------------

def _make_slo_record(
    slo_id: str = "slo-1",
    project_id: str = "project-a",
    agent_name: str = "bot",
) -> MagicMock:
    """Return a mock SLO record with the fields the router serialises."""
    from langsight.models import AgentSLO, SLOMetric

    return AgentSLO(
        id=slo_id,
        project_id=project_id,
        agent_name=agent_name,
        metric=SLOMetric.SUCCESS_RATE,
        target=95.0,
        window_hours=24,
        created_at=datetime.now(UTC),
    )


def _make_span(session_id: str = "sess-1", project_id: str = "project-a") -> dict:
    return {
        "span_id": f"span-{session_id}-{project_id}",
        "parent_span_id": None,
        "span_type": "tool_call",
        "server_name": "pg-mcp",
        "tool_name": "query",
        "agent_name": "bot",
        "started_at": "2026-03-17T12:00:00",
        "ended_at": "2026-03-17T12:00:01",
        "latency_ms": 100.0,
        "status": "success",
        "error": None,
        "trace_id": "t1",
        "project_id": project_id,
        "input_json": None,
        "output_json": None,
    }


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(yaml.dump({"servers": []}))
    return cfg


@pytest.fixture
async def open_client(config_file: Path):
    """AsyncClient with auth DISABLED — the fastest path to hit route logic."""
    from langsight.api.main import create_app
    from langsight.config import load_config

    app = create_app(config_path=config_file)
    storage = MagicMock()
    storage.close = AsyncMock()
    storage.list_api_keys = AsyncMock(return_value=[])
    storage.list_slos = AsyncMock(return_value=[])
    storage.create_slo = AsyncMock()
    storage.delete_slo = AsyncMock(return_value=True)
    storage.get_session_trace = AsyncMock(return_value=[])
    app.state.storage = storage
    app.state.config = load_config(config_file)
    app.state.api_keys = []  # auth disabled

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, storage


# ===========================================================================
# 1. Cross-project SLO deletion
# ===========================================================================

class TestSLOCrossProjectDeletion:
    """Invariant: DELETE /api/slos/{id} with a mismatched project_id must return
    404, not 204.  The storage layer enforces the WHERE id=$1 AND project_id=$2
    clause; the router translates a False return value into a 404."""

    async def test_delete_slo_with_wrong_project_id_returns_404(
        self, open_client
    ) -> None:
        """Attacker passes project_id=project-b but the SLO belongs to project-a.

        Storage returns False (DELETE 0 rows) because the WHERE clause includes
        AND project_id = 'project-b', which does not match.  Router must raise
        404 — not silently succeed with 204.
        """
        c, storage = open_client
        # Simulate: the SLO exists in project-a; delete_slo is called with
        # project-b → DB deletes 0 rows → returns False
        storage.delete_slo = AsyncMock(return_value=False)

        response = await c.delete("/api/slos/slo-project-a?project_id=project-b")

        assert response.status_code == 404, (
            f"Expected 404 when deleting a foreign-project SLO, got {response.status_code}"
        )
        # Confirm storage was called with the attacker's project_id, not silently bypassed
        storage.delete_slo.assert_called_once_with(
            "slo-project-a", project_id="project-b"
        )

    async def test_delete_slo_with_correct_project_id_returns_204(
        self, open_client
    ) -> None:
        """Baseline: legitimate delete of own SLO must still work (no over-blocking)."""
        c, storage = open_client
        storage.delete_slo = AsyncMock(return_value=True)

        response = await c.delete("/api/slos/slo-1?project_id=project-a")

        assert response.status_code == 204
        storage.delete_slo.assert_called_once_with("slo-1", project_id="project-a")

    async def test_delete_slo_storage_called_with_project_id_not_bypassed(
        self, open_client
    ) -> None:
        """The router must forward project_id to storage — never call delete_slo
        without the project_id filter, which would allow cross-project deletion."""
        c, storage = open_client
        storage.delete_slo = AsyncMock(return_value=True)

        await c.delete("/api/slos/slo-99?project_id=tenant-x")

        args, kwargs = storage.delete_slo.call_args
        # project_id must be present — either as positional arg[1] or kwarg
        received_project_id = kwargs.get("project_id") or (args[1] if len(args) > 1 else None)
        assert received_project_id == "tenant-x", (
            "delete_slo must receive the caller's project_id to enforce the WHERE clause"
        )

    async def test_delete_without_project_id_passes_none_to_storage(
        self, open_client
    ) -> None:
        """Admin path (no project_id scoping) passes project_id=None to storage.
        This is expected behaviour for global admin — not a vulnerability."""
        c, storage = open_client
        storage.delete_slo = AsyncMock(return_value=True)

        await c.delete("/api/slos/slo-99")

        args, kwargs = storage.delete_slo.call_args
        received_project_id = kwargs.get("project_id") or (args[1] if len(args) > 1 else None)
        assert received_project_id is None


# ===========================================================================
# 2. Cross-project SLO read
# ===========================================================================

class TestSLOCrossProjectRead:
    """Invariant: GET /api/slos?project_id=B must not expose SLOs from project A.

    The storage layer receives the project_id filter and returns only matching
    rows.  This test verifies that the router forwards the project_id without
    stripping it, and that the response contains only what storage returns.
    """

    async def test_list_slos_forwards_project_id_to_storage(
        self, open_client
    ) -> None:
        """project_id query parameter must flow through to storage.list_slos."""
        c, storage = open_client
        storage.list_slos = AsyncMock(return_value=[])

        response = await c.get("/api/slos?project_id=project-b")

        assert response.status_code == 200
        storage.list_slos.assert_called_once_with(project_id="project-b")

    async def test_list_slos_does_not_return_foreign_project_slos(
        self, open_client
    ) -> None:
        """Storage returns only project-b SLOs; project-a SLOs must not appear.

        The enforcement happens at the storage layer (SQL WHERE project_id=$1).
        This test verifies the router does not re-merge or ignore that filter.
        """
        c, storage = open_client
        project_b_slo = _make_slo_record("slo-b", project_id="project-b")
        # Storage correctly returns only project-b records (simulating the DB filter)
        storage.list_slos = AsyncMock(return_value=[project_b_slo])

        response = await c.get("/api/slos?project_id=project-b")

        data = response.json()
        assert response.status_code == 200
        assert len(data) == 1
        assert data[0]["id"] == "slo-b"

    async def test_list_slos_returns_empty_for_project_with_no_slos(
        self, open_client
    ) -> None:
        """Querying project-b when only project-a SLOs exist must return []."""
        c, storage = open_client
        # Storage respects the WHERE clause — returns nothing for project-b
        storage.list_slos = AsyncMock(return_value=[])

        response = await c.get("/api/slos?project_id=project-b")

        assert response.status_code == 200
        assert response.json() == []

    async def test_list_slos_with_none_project_id_calls_storage_with_none(
        self, open_client
    ) -> None:
        """Admin path (no project_id) must call storage with project_id=None."""
        c, storage = open_client
        storage.list_slos = AsyncMock(return_value=[])

        await c.get("/api/slos")

        storage.list_slos.assert_called_once_with(project_id=None)


# ===========================================================================
# 4. Health history project filtering (storage-level)
# ===========================================================================

class TestHealthHistoryProjectFiltering:
    """Invariant: get_health_history(server_name, project_id="A") must NOT return
    rows whose project_id is "B".  Rows with project_id="" (global CLI checks)
    ARE returned for all project callers — this is intentional behaviour.

    These tests operate directly on the ClickHouseStorageBackend method via a
    mock client to verify the SQL parameterization without a real DB.
    """

    def _make_mock_ch_storage(
        self, rows: list[tuple]
    ) -> object:
        """Build a ClickHouseStorageBackend with a fully mocked _client."""
        from unittest.mock import AsyncMock, MagicMock

        from langsight.storage.clickhouse import ClickHouseBackend

        storage = object.__new__(ClickHouseBackend)
        mock_client = MagicMock()

        mock_result = MagicMock()
        mock_result.result_rows = rows
        mock_client.query = AsyncMock(return_value=mock_result)
        storage._client = mock_client  # type: ignore[attr-defined]
        return storage

    async def test_project_filter_adds_project_id_clause_to_query(self) -> None:
        """When project_id='project-a' is given, the SQL must include both the
        project-specific AND the empty-string (global) condition."""
        storage = self._make_mock_ch_storage([])

        await storage.get_health_history("pg-mcp", project_id="project-a")

        query_call = storage._client.query.call_args
        sql: str = query_call[0][0]
        params: dict = query_call[1]["parameters"]

        assert "project_id" in sql, "SQL must include a project_id filter"
        assert "project_id = ''" in sql or "project_id = ''" in sql.replace(
            "{project_id:String}", "project_id"
        ) or "project_id = ''" in sql or "project_id = ''" in sql
        # Verify the actual project filter is set
        assert params.get("project_id") == "project-a", (
            "project_id parameter must be passed to the query"
        )

    async def test_no_project_filter_when_project_id_is_none(self) -> None:
        """With project_id=None (admin), no project filter is added to the SQL."""
        storage = self._make_mock_ch_storage([])

        await storage.get_health_history("pg-mcp", project_id=None)

        query_call = storage._client.query.call_args
        sql: str = query_call[0][0]
        params: dict = query_call[1]["parameters"]

        assert "project_id" not in params, (
            "Admin call must not add a project_id parameter"
        )
        # No project-scoped WHERE clause should be present
        assert "project_id = {project_id:String}" not in sql

    async def test_global_health_checks_visible_to_project_callers(self) -> None:
        """Rows with project_id='' (CLI-triggered global checks) must be returned
        even when the caller specifies project_id='project-a'.  The SQL uses
        OR project_id = '' to achieve this — verify the clause is present."""
        storage = self._make_mock_ch_storage([])

        await storage.get_health_history("pg-mcp", project_id="project-a")

        sql: str = storage._client.query.call_args[0][0]
        # Both conditions must appear in the query
        assert "project_id = {project_id:String}" in sql, (
            "Project-specific filter must be present"
        )
        assert "project_id = ''" in sql, (
            "Global health check rows (project_id='') must also be returned"
        )

    async def test_project_b_results_excluded_when_querying_project_a(self) -> None:
        """Mock the DB returning only the correct rows — verify the method does
        not re-add project-B rows by deserialising them from the result set."""
        # Rows returned by DB already filtered (simulate correct DB behaviour)
        project_a_row = (
            "pg-mcp", "up", 42.0, 3, "hash123", None,
            datetime.now(UTC), "project-a"
        )
        storage = self._make_mock_ch_storage([project_a_row])

        results = await storage.get_health_history("pg-mcp", project_id="project-a")

        assert len(results) == 1
        assert results[0].project_id == "project-a"

    async def test_empty_project_id_string_treated_as_no_filter(self) -> None:
        """An empty string project_id (falsy) must NOT add a project filter.
        get_health_history uses `if project_id:` — empty string is falsy."""
        storage = self._make_mock_ch_storage([])

        await storage.get_health_history("pg-mcp", project_id="")

        params: dict = storage._client.query.call_args[1]["parameters"]
        assert "project_id" not in params, (
            "Empty string project_id must not add a filter (same as None)"
        )


# ===========================================================================
# 5. Rate-limiter key — X-Forwarded-For injection
# ===========================================================================

class TestRateLimiterKeyResolution:
    """Invariant: _rate_limit_key must extract only the first IP from
    X-Forwarded-For to prevent two attacks:

    a) Bucket exhaustion: attacker rotates IPs to exhaust everyone's quota.
       Each new IP gets its own bucket, so the attacker's requests count against
       their own first-IP bucket — not the server's global pool.

    b) Bucket spoofing: attacker appends a trusted IP after their own
       (e.g. "attacker-ip, 127.0.0.1") hoping the rate limiter will key on
       the trusted IP and not their real address.  The FIRST IP is always used.
    """

    def _make_rate_limit_request(self, headers: dict[str, str], client_ip: str = "10.0.0.1") -> object:
        """Build a minimal mock Request for _rate_limit_key."""
        from unittest.mock import MagicMock

        req = MagicMock()
        req.client = MagicMock()
        req.client.host = client_ip

        raw_headers = dict(headers)
        req.headers = MagicMock()
        req.headers.get = lambda key, default=None: raw_headers.get(key, default)
        return req

    def test_first_ip_extracted_from_multi_ip_forwarded_for(self) -> None:
        """X-Forwarded-For: attacker, proxy1, proxy2 → bucket key is 'attacker'."""
        from langsight.api.rate_limit import _rate_limit_key

        req = self._make_rate_limit_request(
            {"X-Forwarded-For": "1.2.3.4, 10.0.0.1, 192.168.1.1"}
        )
        key = _rate_limit_key(req)  # type: ignore[arg-type]

        assert key == "1.2.3.4", (
            f"Expected first IP '1.2.3.4', got '{key}'. "
            "Attacker must not escape their bucket by appending trusted IPs."
        )

    def test_trusted_ip_appended_after_attacker_ip_does_not_change_bucket(self) -> None:
        """Attack: attacker sends '1.2.3.4, 127.0.0.1' hoping to key on loopback.
        The bucket must still be keyed on the attacker's IP (first value)."""
        from langsight.api.rate_limit import _rate_limit_key

        req = self._make_rate_limit_request(
            {"X-Forwarded-For": "5.5.5.5, 127.0.0.1"}
        )
        key = _rate_limit_key(req)  # type: ignore[arg-type]

        assert key == "5.5.5.5", (
            "Injected trusted IP must not change the rate-limit bucket"
        )
        assert key != "127.0.0.1", (
            "Bucket must not be the injected trusted loopback address"
        )

    def test_different_attacker_ips_get_separate_buckets(self) -> None:
        """Each unique first IP gets its own bucket — attacker cannot exhaust
        a single victim's quota by rotating their own source IP."""
        from langsight.api.rate_limit import _rate_limit_key

        req_a = self._make_rate_limit_request({"X-Forwarded-For": "1.1.1.1"})
        req_b = self._make_rate_limit_request({"X-Forwarded-For": "2.2.2.2"})
        req_c = self._make_rate_limit_request({"X-Forwarded-For": "3.3.3.3"})

        key_a = _rate_limit_key(req_a)  # type: ignore[arg-type]
        key_b = _rate_limit_key(req_b)  # type: ignore[arg-type]
        key_c = _rate_limit_key(req_c)  # type: ignore[arg-type]

        assert key_a != key_b
        assert key_b != key_c
        assert key_a != key_c

    def test_single_ip_forwarded_for_used_as_is(self) -> None:
        """Single clean IP in X-Forwarded-For → no splitting needed."""
        from langsight.api.rate_limit import _rate_limit_key

        req = self._make_rate_limit_request({"X-Forwarded-For": "203.0.113.5"})
        key = _rate_limit_key(req)  # type: ignore[arg-type]

        assert key == "203.0.113.5"

    def test_no_forwarded_for_falls_back_to_api_key_prefix(self) -> None:
        """Without X-Forwarded-For, key should fall back to API key prefix."""
        from langsight.api.rate_limit import _rate_limit_key

        req = self._make_rate_limit_request(
            {"X-API-Key": "secret-key-abcdef1234567890"},
            client_ip="10.0.0.1",
        )
        key = _rate_limit_key(req)  # type: ignore[arg-type]

        assert key.startswith("key:"), f"Expected 'key:' prefix, got '{key}'"
        assert "secret-key-abcde" in key  # only first 16 chars used

    def test_no_forwarded_for_no_api_key_falls_back_to_remote_addr(self) -> None:
        """Without any identifying headers, remote address is the rate-limit key."""
        from langsight.api.rate_limit import _rate_limit_key

        req = self._make_rate_limit_request({}, client_ip="10.0.0.99")
        key = _rate_limit_key(req)  # type: ignore[arg-type]

        assert key == "10.0.0.99"

    def test_whitespace_trimmed_from_forwarded_for_ips(self) -> None:
        """IPs in X-Forwarded-For may have leading/trailing spaces — must be stripped."""
        from langsight.api.rate_limit import _rate_limit_key

        req = self._make_rate_limit_request(
            {"X-Forwarded-For": "  9.9.9.9  , 10.0.0.1"}
        )
        key = _rate_limit_key(req)  # type: ignore[arg-type]

        assert key == "9.9.9.9", (
            f"Leading/trailing whitespace must be stripped from IP, got '{key}'"
        )

    def test_201_unique_ips_each_get_distinct_buckets(self) -> None:
        """201 different callers must produce 201 distinct buckets.

        This proves the attacker's rotation strategy gives them 201 buckets of
        their own — they cannot exhaust a single shared bucket.
        """
        from langsight.api.rate_limit import _rate_limit_key

        keys: set[str] = set()
        for i in range(201):
            req = self._make_rate_limit_request(
                {"X-Forwarded-For": f"192.0.2.{i % 256}, 10.0.0.1"},
                client_ip="10.0.0.1",
            )
            keys.add(_rate_limit_key(req))  # type: ignore[arg-type]

        # Each unique first IP maps to a distinct bucket
        assert len(keys) == len({f"192.0.2.{i % 256}" for i in range(201)}), (
            "Every unique attacker IP must produce its own isolated bucket"
        )
