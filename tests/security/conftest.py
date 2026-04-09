"""
Shared fixtures for the security test suite.

All fixtures here are offline — no Docker, no real DB, no network.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture(autouse=True)
def _clear_api_key_cache() -> None:
    """Clear the auth API key cache before each test."""
    from langsight.api.dependencies import invalidate_api_key_cache

    invalidate_api_key_cache()
import yaml  # noqa: E402
from fastapi import Request  # noqa: E402

# ---------------------------------------------------------------------------
# Low-level request builder (for dependency-function unit tests)
# ---------------------------------------------------------------------------

def _make_request(
    client_ip: str = "127.0.0.1",
    headers: dict[str, str] | None = None,
    api_keys: list[str] | None = None,
    storage: object | None = None,
    trusted_cidrs: str = "127.0.0.1/32,::1/128",
) -> Request:
    """Build a minimal Request-like object for testing auth dependency functions.

    client_ip controls whether proxy headers are trusted (only loopback by
    default).  Callers can set api_keys=["key"] to simulate auth-enabled mode,
    or api_keys=[] for auth-disabled (open install).
    """
    from langsight.api.dependencies import parse_trusted_proxy_networks

    request = MagicMock(spec=Request)
    request.client = MagicMock()
    request.client.host = client_ip

    raw_headers = headers or {}
    request.headers = MagicMock()
    request.headers.get = lambda key, default=None: raw_headers.get(key, default)

    request.url = MagicMock()
    request.url.path = "/api/security-test"
    request.method = "GET"

    app_state = MagicMock()
    app_state.api_keys = api_keys or []
    app_state.storage = storage or _make_storage()
    app_state.trusted_proxy_networks = parse_trusted_proxy_networks(trusted_cidrs)

    request.app = MagicMock()
    request.app.state = app_state
    return request


# ---------------------------------------------------------------------------
# Storage builders
# ---------------------------------------------------------------------------

def _make_storage(
    active_db_keys: list | None = None,
    list_api_keys_raises: Exception | None = None,
    get_member_returns: object | None = None,
    get_member_raises: Exception | None = None,
) -> MagicMock:
    """Return a mock StorageBackend with configurable behaviour."""
    storage = MagicMock()
    storage.list_members = AsyncMock(return_value=[])

    if list_api_keys_raises:
        storage.list_api_keys = AsyncMock(side_effect=list_api_keys_raises)
    else:
        storage.list_api_keys = AsyncMock(return_value=active_db_keys or [])

    if get_member_raises:
        storage.get_member = AsyncMock(side_effect=get_member_raises)
    else:
        storage.get_member = AsyncMock(return_value=get_member_returns)

    storage.get_api_key_by_hash = AsyncMock(return_value=None)
    return storage


def _active_key_record(key_id: str = "key-1", role: str = "viewer") -> MagicMock:
    from langsight.models import ApiKeyRole
    rec = MagicMock()
    rec.id = key_id
    rec.is_revoked = False
    rec.role = ApiKeyRole.ADMIN if role == "admin" else ApiKeyRole.VIEWER
    return rec


def _revoked_key_record(key_id: str = "key-revoked") -> MagicMock:
    rec = MagicMock()
    rec.id = key_id
    rec.is_revoked = True
    return rec


def _member_record(project_id: str = "proj-1", user_id: str = "user-1") -> MagicMock:
    from langsight.models import ProjectRole
    mem = MagicMock()
    mem.project_id = project_id
    mem.user_id = user_id
    mem.role = ProjectRole.MEMBER
    return mem


# ---------------------------------------------------------------------------
# HTTP test client builder (for endpoint-level tests)
# ---------------------------------------------------------------------------

@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(yaml.dump({"servers": [], "auth_disabled": True}))
    return cfg


@pytest.fixture
async def auth_client(config_file: Path):
    """AsyncClient with auth ENABLED (one env key: 'test-api-key').

    Use this to test that unauthenticated or wrongly-authenticated requests
    are correctly rejected.
    """
    from httpx import ASGITransport, AsyncClient

    from langsight.api.main import create_app
    from langsight.config import load_config

    app = create_app(config_path=config_file)
    mock_storage = MagicMock()
    mock_storage.get_health_history = AsyncMock(return_value=[])
    mock_storage.list_api_keys = AsyncMock(return_value=[])
    mock_storage.close = AsyncMock()

    app.state.storage = mock_storage
    app.state.config = load_config(config_file)
    app.state.api_keys = ["test-api-key"]   # auth IS enabled

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, mock_storage, app


@pytest.fixture
async def open_client(config_file: Path):
    """AsyncClient with auth DISABLED (no keys anywhere).

    Use this to verify open-install behaviour still works correctly.
    """
    from httpx import ASGITransport, AsyncClient

    from langsight.api.main import create_app
    from langsight.config import load_config

    app = create_app(config_path=config_file)
    mock_storage = MagicMock()
    mock_storage.get_health_history = AsyncMock(return_value=[])
    mock_storage.list_api_keys = AsyncMock(return_value=[])
    mock_storage.close = AsyncMock()

    app.state.storage = mock_storage
    app.state.config = load_config(config_file)
    app.state.api_keys = []   # auth disabled

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, mock_storage, app
