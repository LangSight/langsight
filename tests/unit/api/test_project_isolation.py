"""
Unit tests for project isolation model behaviour and HealthChecker project_id stamping.

Covers:
  - ApiKeyRecord.project_id round-trip and None default
  - HealthChecker stamps project_id on UP, DOWN (timeout), and DOWN (connection error) results
  - Default project_id for HealthChecker constructed without argument

All tests run offline — no Docker, no DB, no network.
"""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from langsight.models import (
    ApiKeyRecord,
    ApiKeyRole,
    HealthCheckResult,
    MCPServer,
    ServerStatus,
    TransportType,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# ApiKeyRecord — project_id field
# ---------------------------------------------------------------------------


class TestApiKeyRecordProjectId:
    def test_api_key_project_id_stored_and_retrieved(self) -> None:
        """Creating ApiKeyRecord with project_id='proj-x' must round-trip correctly."""
        record = ApiKeyRecord(
            id="key-id-1",
            name="test key",
            key_prefix="ls_12345",
            key_hash="a" * 64,
            role=ApiKeyRole.VIEWER,
            project_id="proj-x",
        )
        assert record.project_id == "proj-x"

    def test_api_key_without_project_id_is_none(self) -> None:
        """ApiKeyRecord constructed without project_id → project_id is None."""
        record = ApiKeyRecord(
            id="key-id-2",
            name="global key",
            key_prefix="ls_67890",
            key_hash="b" * 64,
            role=ApiKeyRole.ADMIN,
        )
        assert record.project_id is None

    def test_api_key_project_id_explicit_none_is_none(self) -> None:
        """Explicitly passing project_id=None also results in project_id is None."""
        record = ApiKeyRecord(
            id="key-id-3",
            name="none key",
            key_prefix="ls_abcde",
            key_hash="c" * 64,
            role=ApiKeyRole.VIEWER,
            project_id=None,
        )
        assert record.project_id is None

    def test_api_key_with_project_id_is_not_active_when_revoked(self) -> None:
        """A project-scoped key that is revoked must not be active."""
        record = ApiKeyRecord(
            id="key-id-4",
            name="revoked key",
            key_prefix="ls_fghij",
            key_hash="d" * 64,
            role=ApiKeyRole.VIEWER,
            project_id="proj-y",
            revoked_at=datetime.now(UTC),
        )
        assert record.project_id == "proj-y"
        assert record.is_revoked is True
        assert record.is_active is False

    def test_api_key_with_project_id_preserves_role(self) -> None:
        """project_id must not affect the role field."""
        record = ApiKeyRecord(
            id="key-id-5",
            name="scoped admin",
            key_prefix="ls_klmno",
            key_hash="e" * 64,
            role=ApiKeyRole.ADMIN,
            project_id="proj-z",
        )
        assert record.project_id == "proj-z"
        assert record.role == ApiKeyRole.ADMIN


# ---------------------------------------------------------------------------
# HealthChecker — project_id stamped on all result types
# ---------------------------------------------------------------------------


def _make_server(name: str = "test-server") -> MCPServer:
    return MCPServer(
        name=name,
        transport=TransportType.STDIO,
        command="echo",
    )


class TestHealthCheckerProjectIdStamping:
    async def test_health_checker_stamps_project_id_on_up_result(self) -> None:
        """HealthChecker(project_id='proj-x') stamps 'proj-x' on UP results."""
        from langsight.health.checker import HealthChecker

        server = _make_server()
        with patch("langsight.health.checker.ping") as mock_ping, \
             patch("langsight.health.checker.hash_tools") as mock_hash:
            mock_ping.return_value = (42.0, [])
            mock_hash.return_value = "schema-hash-abc"

            checker = HealthChecker(project_id="proj-x")
            result = await checker.check(server)

        assert result.project_id == "proj-x"
        assert result.status == ServerStatus.UP

    async def test_health_checker_default_project_is_empty_string(self) -> None:
        """HealthChecker() without project_id → project_id == '' on results."""
        from langsight.health.checker import HealthChecker

        server = _make_server()
        with patch("langsight.health.checker.ping") as mock_ping, \
             patch("langsight.health.checker.hash_tools") as mock_hash:
            mock_ping.return_value = (10.0, [])
            mock_hash.return_value = "hash-xyz"

            checker = HealthChecker()
            result = await checker.check(server)

        assert result.project_id == ""

    async def test_health_checker_timeout_result_carries_project_id(self) -> None:
        """Timeout (DOWN) results must also carry the project_id."""
        from langsight.exceptions import MCPTimeoutError
        from langsight.health.checker import HealthChecker

        server = _make_server()
        with patch("langsight.health.checker.ping") as mock_ping:
            mock_ping.side_effect = MCPTimeoutError("timeout after 5s")

            checker = HealthChecker(project_id="proj-timeout")
            result = await checker.check(server)

        assert result.project_id == "proj-timeout"
        assert result.status == ServerStatus.DOWN
        assert "timeout" in (result.error or "").lower()

    async def test_health_checker_down_result_carries_project_id(self) -> None:
        """Connection error (DOWN) results must also carry the project_id."""
        from langsight.exceptions import MCPConnectionError
        from langsight.health.checker import HealthChecker

        server = _make_server()
        with patch("langsight.health.checker.ping") as mock_ping:
            mock_ping.side_effect = MCPConnectionError("refused")

            checker = HealthChecker(project_id="proj-down")
            result = await checker.check(server)

        assert result.project_id == "proj-down"
        assert result.status == ServerStatus.DOWN

    async def test_health_checker_unexpected_error_carries_project_id(self) -> None:
        """Unexpected exceptions still produce a DOWN result with the project_id."""
        from langsight.health.checker import HealthChecker

        server = _make_server()
        with patch("langsight.health.checker.ping") as mock_ping:
            mock_ping.side_effect = RuntimeError("something exploded")

            checker = HealthChecker(project_id="proj-unexpected")
            result = await checker.check(server)

        assert result.project_id == "proj-unexpected"
        assert result.status == ServerStatus.DOWN

    async def test_health_checker_empty_project_id_on_timeout(self) -> None:
        """HealthChecker() (default project) → project_id='' even on timeout."""
        from langsight.exceptions import MCPTimeoutError
        from langsight.health.checker import HealthChecker

        server = _make_server()
        with patch("langsight.health.checker.ping") as mock_ping:
            mock_ping.side_effect = MCPTimeoutError("timed out")

            checker = HealthChecker()
            result = await checker.check(server)

        assert result.project_id == ""

    async def test_health_checker_project_id_persisted_to_storage(self) -> None:
        """When storage is provided, the saved result carries the project_id."""
        from langsight.health.checker import HealthChecker

        server = _make_server()
        mock_storage = MagicMock()
        mock_storage.save_health_result = AsyncMock()

        with patch("langsight.health.checker.ping") as mock_ping, \
             patch("langsight.health.checker.hash_tools") as mock_hash:
            mock_ping.return_value = (25.0, [])
            mock_hash.return_value = "hash-123"

            checker = HealthChecker(storage=mock_storage, project_id="stored-project")
            result = await checker.check(server)

        mock_storage.save_health_result.assert_called_once()
        saved: HealthCheckResult = mock_storage.save_health_result.call_args[0][0]
        assert saved.project_id == "stored-project"

    async def test_health_checker_stores_empty_project_id_when_not_set(self) -> None:
        """HealthChecker without project_id stores empty string (not None)."""
        from langsight.health.checker import HealthChecker

        server = _make_server()
        mock_storage = MagicMock()
        mock_storage.save_health_result = AsyncMock()

        with patch("langsight.health.checker.ping") as mock_ping, \
             patch("langsight.health.checker.hash_tools") as mock_hash:
            mock_ping.return_value = (15.0, [])
            mock_hash.return_value = "hash-456"

            checker = HealthChecker(storage=mock_storage)
            result = await checker.check(server)

        saved: HealthCheckResult = mock_storage.save_health_result.call_args[0][0]
        assert saved.project_id == ""  # empty string — not None


# ---------------------------------------------------------------------------
# HealthCheckResult — project_id field model-level
# ---------------------------------------------------------------------------


class TestHealthCheckResultProjectId:
    def test_health_check_result_default_project_id_is_empty(self) -> None:
        """HealthCheckResult built without project_id has project_id='' by default."""
        result = HealthCheckResult(
            server_name="srv",
            status=ServerStatus.UP,
            latency_ms=10.0,
        )
        assert result.project_id == ""

    def test_health_check_result_stores_project_id(self) -> None:
        """Explicitly setting project_id on HealthCheckResult round-trips correctly."""
        result = HealthCheckResult(
            server_name="srv",
            status=ServerStatus.UP,
            latency_ms=10.0,
            project_id="proj-abc",
        )
        assert result.project_id == "proj-abc"

    def test_health_check_result_down_carries_project_id(self) -> None:
        """DOWN status result can carry a project_id (model-level check)."""
        result = HealthCheckResult(
            server_name="srv",
            status=ServerStatus.DOWN,
            error="connection refused",
            project_id="proj-down",
        )
        assert result.project_id == "proj-down"
        assert result.status == ServerStatus.DOWN
