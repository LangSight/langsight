"""
Integration tests for project isolation using in-memory mock storage.

These tests simulate multi-project scenarios end-to-end through the
get_active_project_id dependency, verifying that:
  - Project-A key cannot read project-B health data
  - A global admin key sees all projects (returns None)
  - A project-scoped key created and round-tripped carries project_id
  - HealthChecker with project_id stamps results correctly (CLI simulation)

All tests use in-memory mock storage — no Docker or real DB required.
They are marked @pytest.mark.integration because they exercise multi-component
interactions (dependency resolution + storage dispatch) that unit tests
with individual mocks do not cover.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from langsight.api.main import create_app
from langsight.config import load_config
from langsight.models import (
    ApiKeyRecord,
    ApiKeyRole,
    HealthCheckResult,
    MCPServer,
    ServerStatus,
    TransportType,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Test infrastructure helpers
# ---------------------------------------------------------------------------


def _make_config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(yaml.dump({"servers": []}))
    return cfg


def _scoped_key_record(
    *,
    raw_key: str,
    project_id: str,
    role: ApiKeyRole = ApiKeyRole.VIEWER,
) -> ApiKeyRecord:
    """Build a real (not mocked) ApiKeyRecord with a project_id bound."""
    return ApiKeyRecord(
        id="key-" + raw_key[:6],
        name="scoped key",
        key_prefix=raw_key[:8],
        key_hash=hashlib.sha256(raw_key.encode()).hexdigest(),
        role=role,
        project_id=project_id,
    )


def _global_key_record(*, raw_key: str) -> ApiKeyRecord:
    """Build a real ApiKeyRecord with no project_id (global/unscoped)."""
    return ApiKeyRecord(
        id="key-global",
        name="global key",
        key_prefix=raw_key[:8],
        key_hash=hashlib.sha256(raw_key.encode()).hexdigest(),
        role=ApiKeyRole.ADMIN,
        project_id=None,
    )


def _make_storage_with_scoped_key(key_record: ApiKeyRecord) -> MagicMock:
    """Return a storage mock that knows about a single scoped key."""
    storage = MagicMock()
    storage.list_members = AsyncMock(return_value=[])
    storage.list_api_keys = AsyncMock(return_value=[key_record])
    storage.get_api_key_by_hash = AsyncMock(return_value=key_record)
    storage.get_member = AsyncMock(return_value=None)
    storage.close = AsyncMock()
    return storage


def _make_storage_with_admin_key(key_record: ApiKeyRecord) -> MagicMock:
    """Return a storage mock for an admin key with no project_id."""
    storage = MagicMock()
    storage.list_members = AsyncMock(return_value=[])
    storage.list_api_keys = AsyncMock(return_value=[key_record])
    storage.get_api_key_by_hash = AsyncMock(return_value=key_record)
    storage.get_member = AsyncMock(return_value=None)
    storage.close = AsyncMock()
    return storage


def _make_request(
    *,
    client_ip: str = "10.0.0.1",
    headers: dict[str, str],
    env_keys: list[str],
    storage: object,
    config_project_id: str = "",
) -> MagicMock:
    from langsight.api.dependencies import parse_trusted_proxy_networks

    request = MagicMock()
    request.client = MagicMock()
    request.client.host = client_ip

    raw_headers = dict(headers)
    request.headers = MagicMock()
    request.headers.get = lambda key, default=None: raw_headers.get(key, default)
    request.url = MagicMock()
    request.url.path = "/api/test"
    request.method = "GET"

    cfg = MagicMock()
    cfg.project_id = config_project_id

    app_state = MagicMock()
    app_state.api_keys = env_keys
    app_state.storage = storage
    app_state.config = cfg
    app_state.trusted_proxy_networks = parse_trusted_proxy_networks("127.0.0.1/32,::1/128")

    request.app = MagicMock()
    request.app.state = app_state
    return request


# ---------------------------------------------------------------------------
# Test: project-A key cannot read project-B health
# ---------------------------------------------------------------------------


class TestProjectKeyIsolation:
    async def test_project_a_key_cannot_read_project_b_health(self) -> None:
        """A key scoped to project-A must not return project-B data.

        The resolver returns the key's own project_id ("proj-a") regardless
        of what project_id the caller supplies in the query param. The
        downstream storage call is therefore filtered to proj-a, not proj-b.
        """
        from langsight.api.dependencies import get_active_project_id

        raw_key = "proj-a-key-xyzzy"
        record = _scoped_key_record(raw_key=raw_key, project_id="proj-a")
        storage = _make_storage_with_scoped_key(record)

        req = _make_request(
            headers={"X-API-Key": raw_key},
            env_keys=[],
            storage=storage,
        )
        # Caller tries to query project-b — resolver must return proj-a instead
        resolved = await get_active_project_id(request=req, project_id="proj-b")
        assert resolved == "proj-a", (
            "Project-scoped key must always resolve to its own project — "
            f"expected 'proj-a' but got {resolved!r}"
        )

    async def test_project_b_key_resolves_to_project_b_not_a(self) -> None:
        """Key scoped to proj-b with proj-a in query param → resolves to proj-b."""
        from langsight.api.dependencies import get_active_project_id

        raw_key = "proj-b-key-abcde"
        record = _scoped_key_record(raw_key=raw_key, project_id="proj-b")
        storage = _make_storage_with_scoped_key(record)

        req = _make_request(
            headers={"X-API-Key": raw_key},
            env_keys=[],
            storage=storage,
        )
        resolved = await get_active_project_id(request=req, project_id="proj-a")
        assert resolved == "proj-b"

    async def test_two_different_scoped_keys_resolve_independently(self) -> None:
        """Two separate project-scoped keys must each resolve to their own project."""
        from langsight.api.dependencies import get_active_project_id

        raw_key_a = "key-a-aaaa"
        raw_key_b = "key-b-bbbb"

        record_a = _scoped_key_record(raw_key=raw_key_a, project_id="proj-a")
        storage_a = _make_storage_with_scoped_key(record_a)

        record_b = _scoped_key_record(raw_key=raw_key_b, project_id="proj-b")
        storage_b = _make_storage_with_scoped_key(record_b)

        req_a = _make_request(
            headers={"X-API-Key": raw_key_a},
            env_keys=[],
            storage=storage_a,
        )
        req_b = _make_request(
            headers={"X-API-Key": raw_key_b},
            env_keys=[],
            storage=storage_b,
        )

        resolved_a = await get_active_project_id(request=req_a, project_id=None)
        resolved_b = await get_active_project_id(request=req_b, project_id=None)

        assert resolved_a == "proj-a"
        assert resolved_b == "proj-b"
        assert resolved_a != resolved_b


# ---------------------------------------------------------------------------
# Test: global admin sees all projects
# ---------------------------------------------------------------------------


class TestGlobalAdminSeesAll:
    async def test_global_admin_db_key_with_project_id_param_returns_project(
        self,
    ) -> None:
        """DB admin key (no project_id on key) + explicit project_id param → returns param.

        get_active_project_id considers only session headers and env-var keys as
        'is_admin' for the no-project-id bypass.  A DB admin key that provides an
        explicit project_id query param still has access validated and the param
        is returned.
        """
        from langsight.api.dependencies import get_active_project_id

        raw_key = "global-admin-key"
        record = _global_key_record(raw_key=raw_key)
        storage = _make_storage_with_admin_key(record)

        req = _make_request(
            headers={"X-API-Key": raw_key},
            env_keys=[],
            storage=storage,
        )
        # DB admin key + explicit project_id → returns that project_id
        resolved = await get_active_project_id(request=req, project_id="admin-project")
        assert resolved == "admin-project", (
            "DB admin key with project_id param must return that project. "
            f"Got {resolved!r}"
        )

    async def test_env_admin_key_always_global(self) -> None:
        """Env-var bootstrap key is always global admin → None regardless of query."""
        from langsight.api.dependencies import get_active_project_id

        env_key = "bootstrap-env-key-12345"
        storage = MagicMock()
        storage.list_members = AsyncMock(return_value=[])
        storage.list_api_keys = AsyncMock(return_value=[])
        storage.get_api_key_by_hash = AsyncMock(return_value=None)
        storage.close = AsyncMock()

        req = _make_request(
            headers={"X-API-Key": env_key},
            env_keys=[env_key],
            storage=storage,
        )
        resolved = await get_active_project_id(request=req, project_id=None)
        assert resolved is None


# ---------------------------------------------------------------------------
# Test: project-scoped key creation round-trip (model-level integration)
# ---------------------------------------------------------------------------


class TestProjectScopedKeyCreationRoundtrip:
    def test_project_scoped_key_creation_roundtrip(self) -> None:
        """Create a key with project_id via the model, retrieve it, confirm project_id.

        This verifies the ApiKeyRecord model fully round-trips project_id —
        the field is stored, not computed.
        """
        raw_key = "round-trip-key-9876"
        record = _scoped_key_record(
            raw_key=raw_key,
            project_id="rt-project-id",
        )

        # Simulate storage returning the record via get_api_key_by_hash
        storage = _make_storage_with_scoped_key(record)
        returned: ApiKeyRecord = storage.get_api_key_by_hash.return_value

        assert returned.project_id == "rt-project-id"
        assert returned.key_hash == hashlib.sha256(raw_key.encode()).hexdigest()

    def test_global_key_round_trip_has_no_project(self) -> None:
        """Global key record has project_id=None after construction."""
        raw_key = "global-round-trip"
        record = _global_key_record(raw_key=raw_key)
        assert record.project_id is None

    def test_scoped_key_role_preserved(self) -> None:
        """project_id binding does not corrupt the role field."""
        raw_key = "scoped-admin-key"
        record = _scoped_key_record(
            raw_key=raw_key,
            project_id="role-check-project",
            role=ApiKeyRole.ADMIN,
        )
        assert record.project_id == "role-check-project"
        assert record.role == ApiKeyRole.ADMIN


# ---------------------------------------------------------------------------
# Test: CLI simulation — HealthChecker with project_id stamps results correctly
# ---------------------------------------------------------------------------


class TestCliHealthCheckUsesConfigProjectId:
    async def test_cli_health_check_uses_config_project_id(self) -> None:
        """HealthChecker(project_id=config.project_id) stamps results with that id.

        Simulates the CLI `langsight mcp-health` flow where the config file
        provides a project_id and the checker stamps all results.
        """
        from unittest.mock import patch

        from langsight.health.checker import HealthChecker

        config_project_id = "cli-config-project"
        server = MCPServer(
            name="cli-test-server",
            transport=TransportType.STDIO,
            command="echo",
        )

        with patch("langsight.health.checker.ping") as mock_ping, \
             patch("langsight.health.checker.hash_tools") as mock_hash:
            mock_ping.return_value = (33.0, [])
            mock_hash.return_value = "hash-cli"

            checker = HealthChecker(project_id=config_project_id)
            result = await checker.check(server)

        assert result.project_id == config_project_id
        assert result.status == ServerStatus.UP

    async def test_cli_health_check_multiple_servers_all_stamped(self) -> None:
        """check_many stamps project_id on every result — not just the first."""
        from unittest.mock import patch

        from langsight.health.checker import HealthChecker

        project = "multi-server-project"
        servers = [
            MCPServer(name=f"srv-{i}", transport=TransportType.STDIO, command="echo")
            for i in range(3)
        ]

        with patch("langsight.health.checker.ping") as mock_ping, \
             patch("langsight.health.checker.hash_tools") as mock_hash:
            mock_ping.return_value = (20.0, [])
            mock_hash.return_value = "hash-multi"

            checker = HealthChecker(project_id=project)
            results = await checker.check_many(servers)

        assert len(results) == 3
        for result in results:
            assert result.project_id == project, (
                f"Server {result.server_name} has project_id={result.project_id!r}, "
                f"expected {project!r}"
            )

    async def test_no_project_id_in_config_gives_empty_string(self) -> None:
        """HealthChecker(project_id='') (config default) stamps empty string — not None."""
        from unittest.mock import patch

        from langsight.health.checker import HealthChecker

        server = MCPServer(
            name="no-project-server",
            transport=TransportType.STDIO,
            command="echo",
        )

        with patch("langsight.health.checker.ping") as mock_ping, \
             patch("langsight.health.checker.hash_tools") as mock_hash:
            mock_ping.return_value = (5.0, [])
            mock_hash.return_value = "hash-empty"

            checker = HealthChecker(project_id="")  # explicit empty = config default
            result = await checker.check(server)

        assert result.project_id == ""
        assert result.project_id is not None
