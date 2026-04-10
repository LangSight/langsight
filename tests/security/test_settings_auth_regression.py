"""
Security regression tests — /api/settings auth bypass (CVE fix).

Bug fixed:
    GET /api/settings and PUT /api/settings were registered directly on the
    FastAPI app instance without auth dependencies, bypassing the router-level
    ``dependencies=[Depends(verify_api_key)]`` applied to every other route.

    An unauthenticated caller could:
      - GET /api/settings → read global instance configuration (200)
      - PUT /api/settings → overwrite instance configuration, e.g. disable
        payload redaction (200), with no credentials whatsoever

Fix applied (src/langsight/api/main.py):
    GET /api/settings  → dependencies=[Depends(verify_api_key)]
    PUT /api/settings  → dependencies=[Depends(verify_api_key), Depends(require_admin)]

This file proves those guards now hold and will catch any future regression
that removes or weakens them.

Also tested here: SSE project-isolation filter correctness — a span:new event
carrying project_id=B must NOT reach a subscriber scoped to project_id=A.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

pytestmark = [pytest.mark.security, pytest.mark.regression]

# ---------------------------------------------------------------------------
# Fixtures — auth-enabled and open-install HTTP clients, plus a viewer client
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _set_proxy_secret(monkeypatch):
    """Set LANGSIGHT_PROXY_SECRET for all tests in this module."""
    from tests.security.conftest import _TEST_PROXY_SECRET

    monkeypatch.setenv("LANGSIGHT_PROXY_SECRET", _TEST_PROXY_SECRET)


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    """Minimal .langsight.yaml with no servers, suitable for all settings tests."""
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(yaml.dump({"servers": [], "auth_disabled": True}))
    return cfg


def _make_mock_storage(
    *,
    has_instance_settings: bool = True,
    get_instance_settings_returns: dict | None = None,
    save_instance_settings_raises: Exception | None = None,
) -> MagicMock:
    """Build a minimal mock storage appropriate for settings endpoint tests.

    Controls whether save_instance_settings is present on the mock, so tests
    can assert it was never called on unauthenticated attempts.
    """
    storage = MagicMock()
    storage.get_health_history = AsyncMock(return_value=[])
    storage.list_api_keys = AsyncMock(return_value=[])
    storage.close = AsyncMock()
    storage.ping = AsyncMock(return_value={"postgres": "ok"})

    if has_instance_settings:
        settings_data = get_instance_settings_returns or {"redact_payloads": False}
        storage.get_instance_settings = AsyncMock(return_value=settings_data)
        if save_instance_settings_raises:
            storage.save_instance_settings = AsyncMock(
                side_effect=save_instance_settings_raises
            )
        else:
            storage.save_instance_settings = AsyncMock(return_value=None)
    else:
        # Storage backend that does NOT implement instance settings
        del storage.get_instance_settings
        del storage.save_instance_settings

    return storage


def _build_app(config_file: Path, api_keys: list[str], storage: MagicMock):
    """Construct a fully-wired FastAPI app without going through lifespan.

    We bypass lifespan to avoid hitting real DB bootstrap code. State is set
    directly on app.state — exactly as the production lifespan does it.
    """
    import ipaddress

    from langsight.api.dependencies import invalidate_api_key_cache
    from langsight.api.main import create_app
    from langsight.config import load_config

    invalidate_api_key_cache()

    app = create_app(config_path=config_file)
    app.state.storage = storage
    app.state.config = load_config(config_file)
    app.state.api_keys = api_keys
    app.state.dashboard_url = "http://localhost:3002"
    app.state.trusted_proxy_networks = [
        ipaddress.ip_network("127.0.0.1/32"),
        ipaddress.ip_network("::1/128"),
    ]

    # alert_types must be populated to avoid AttributeError in alerts router
    from langsight.api.routers.alerts_config import _DEFAULT_ALERT_TYPES

    app.state.alert_types = dict(_DEFAULT_ALERT_TYPES)

    return app


@pytest.fixture
async def auth_client_with_storage(config_file: Path):
    """AsyncClient against auth-ENABLED app (one env key: 'test-api-key').

    Yields (client, mock_storage) so tests can assert on mock_storage calls.
    """
    from httpx import ASGITransport, AsyncClient

    from langsight.api.dependencies import invalidate_api_key_cache

    invalidate_api_key_cache()
    storage = _make_mock_storage()
    app = _build_app(config_file, api_keys=["test-api-key"], storage=storage)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, storage


@pytest.fixture
async def open_client_with_storage(config_file: Path):
    """AsyncClient against auth-DISABLED app (no keys configured).

    Open-install behaviour: unauthenticated requests must be allowed through.
    """
    from httpx import ASGITransport, AsyncClient

    from langsight.api.dependencies import invalidate_api_key_cache

    invalidate_api_key_cache()
    storage = _make_mock_storage()
    app = _build_app(config_file, api_keys=[], storage=storage)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, storage


@pytest.fixture
async def viewer_client_with_storage(config_file: Path):
    """AsyncClient that presents a DB-stored viewer-role key.

    Storage returns a viewer-role ApiKeyRecord when get_api_key_by_hash is called.
    api_keys is empty so the env-key shortcut does not apply.
    """
    import hashlib

    from httpx import ASGITransport, AsyncClient

    from langsight.api.dependencies import invalidate_api_key_cache
    from langsight.models import ApiKeyRole

    invalidate_api_key_cache()

    viewer_secret = "viewer-secret-key-for-settings-test"
    hashlib.sha256(viewer_secret.encode()).hexdigest()

    viewer_record = MagicMock()
    viewer_record.id = "viewer-key-id"
    viewer_record.is_revoked = False
    viewer_record.is_expired = False
    viewer_record.role = ApiKeyRole.VIEWER
    viewer_record.user_id = None

    storage = _make_mock_storage()
    # Auth is enabled because there is an active DB key
    storage.list_api_keys = AsyncMock(return_value=[viewer_record])
    storage.get_api_key_by_hash = AsyncMock(return_value=viewer_record)
    storage.touch_api_key = AsyncMock(return_value=None)

    app = _build_app(config_file, api_keys=[], storage=storage)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, storage, viewer_secret


# ===========================================================================
# Class 1 — Unauthenticated GET /api/settings must return 401
# ===========================================================================


class TestUnauthenticatedGetSettings:
    """Invariant: GET /api/settings must require authentication.

    The specific regression: before the fix this endpoint was mounted without
    Depends(verify_api_key), so any caller could read global instance settings
    with no credentials.
    """

    async def test_no_key_returns_401(self, auth_client_with_storage) -> None:
        """Core regression: unauthenticated GET must NOT return 200."""
        c, _ = auth_client_with_storage
        response = await c.get("/api/settings")
        assert response.status_code == 401, (
            f"Expected 401 (unauthenticated), got {response.status_code}. "
            "This is the exact regression: /api/settings must enforce verify_api_key."
        )

    async def test_no_key_does_not_leak_settings_body(self, auth_client_with_storage) -> None:
        """Even if status code were wrong, no settings data must appear in the body."""
        c, _ = auth_client_with_storage
        response = await c.get("/api/settings")
        # Must not contain recognisable settings payload keys
        assert response.status_code != 200
        body_text = response.text
        assert "redact_payloads" not in body_text, (
            "Settings payload leaked to unauthenticated caller."
        )

    async def test_empty_bearer_token_returns_401(self, auth_client_with_storage) -> None:
        """Authorization: Bearer (empty value) is not a valid credential."""
        c, _ = auth_client_with_storage
        response = await c.get("/api/settings", headers={"Authorization": "Bearer "})
        assert response.status_code == 401

    async def test_wrong_key_returns_403(self, auth_client_with_storage) -> None:
        """A wrong key is different from no key: must return 403 not 200."""
        c, _ = auth_client_with_storage
        response = await c.get("/api/settings", headers={"X-API-Key": "totally-wrong"})
        assert response.status_code == 403

    async def test_valid_key_returns_200(self, auth_client_with_storage) -> None:
        """Positive control: valid env key must still succeed (no regression on the happy path)."""
        c, _ = auth_client_with_storage
        response = await c.get("/api/settings", headers={"X-API-Key": "test-api-key"})
        assert response.status_code == 200

    async def test_open_install_allows_unauthenticated_get(self, open_client_with_storage) -> None:
        """Open-install (no keys configured) must still allow unauthenticated access.

        This guards against over-correction: the fix must not break open installs.
        """
        c, _ = open_client_with_storage
        response = await c.get("/api/settings")
        assert response.status_code == 200


# ===========================================================================
# Class 2 — Unauthenticated PUT /api/settings must return 401 and never write
# ===========================================================================


class TestUnauthenticatedPutSettings:
    """Invariant: PUT /api/settings must require authentication and admin role.

    The specific regression: before the fix, any HTTP client that knew the
    endpoint existed could write arbitrary settings — including disabling payload
    redaction — with no credentials. save_instance_settings must NEVER be called
    on an unauthenticated request.
    """

    async def test_no_key_returns_401(self, auth_client_with_storage) -> None:
        """Core regression: unauthenticated PUT must NOT return 200."""
        c, _ = auth_client_with_storage
        response = await c.put("/api/settings", json={"redact_payloads": True})
        assert response.status_code == 401, (
            f"Expected 401 (unauthenticated), got {response.status_code}. "
            "This is the exact regression: /api/settings PUT must enforce verify_api_key."
        )

    async def test_save_instance_settings_not_called_on_no_key(
        self, auth_client_with_storage
    ) -> None:
        """save_instance_settings must never be invoked on unauthenticated PUT.

        This is the critical assertion: the mock proves the storage layer was
        never reached, meaning the auth guard fired before the handler executed.
        """
        c, storage = auth_client_with_storage
        await c.put("/api/settings", json={"redact_payloads": True})
        storage.save_instance_settings.assert_not_called()

    async def test_wrong_key_returns_403_and_does_not_write(
        self, auth_client_with_storage
    ) -> None:
        """An invalid API key must be rejected at 403 and must not trigger a write."""
        c, storage = auth_client_with_storage
        response = await c.put(
            "/api/settings",
            json={"redact_payloads": True},
            headers={"X-API-Key": "not-the-right-key"},
        )
        assert response.status_code == 403
        storage.save_instance_settings.assert_not_called()

    async def test_empty_bearer_returns_401_and_does_not_write(
        self, auth_client_with_storage
    ) -> None:
        """'Authorization: Bearer ' (empty token) must not reach the handler."""
        c, storage = auth_client_with_storage
        response = await c.put(
            "/api/settings",
            json={"redact_payloads": False},
            headers={"Authorization": "Bearer "},
        )
        assert response.status_code == 401
        storage.save_instance_settings.assert_not_called()

    async def test_valid_admin_key_calls_save_and_returns_200(
        self, auth_client_with_storage
    ) -> None:
        """Positive control: a valid admin env key must be able to write settings."""
        c, storage = auth_client_with_storage
        response = await c.put(
            "/api/settings",
            json={"redact_payloads": True},
            headers={"X-API-Key": "test-api-key"},
        )
        assert response.status_code == 200
        storage.save_instance_settings.assert_called_once()


# ===========================================================================
# Class 3 — Non-admin (viewer role) PUT /api/settings must return 403
# ===========================================================================


class TestNonAdminPutSettings:
    """Invariant: PUT /api/settings requires admin role, not just any valid key.

    A viewer-role DB key is authenticated (verify_api_key passes) but must be
    rejected by require_admin with 403. The write must never reach storage.
    """

    async def test_viewer_db_key_returns_403(self, viewer_client_with_storage) -> None:
        """Authenticated viewer must be blocked from writing settings — 403, not 200."""
        c, _, viewer_secret = viewer_client_with_storage
        response = await c.put(
            "/api/settings",
            json={"redact_payloads": True},
            headers={"X-API-Key": viewer_secret},
        )
        assert response.status_code == 403, (
            f"Expected 403 (forbidden for non-admin), got {response.status_code}. "
            "Viewer-role key must not be able to write instance settings."
        )

    async def test_viewer_db_key_does_not_trigger_save(
        self, viewer_client_with_storage
    ) -> None:
        """save_instance_settings must NOT be called when the caller is a viewer.

        This distinguishes a correct 403 (guard fired before handler) from a
        handler error that accidentally returns 403 after writing.
        """
        c, storage, viewer_secret = viewer_client_with_storage
        await c.put(
            "/api/settings",
            json={"redact_payloads": True},
            headers={"X-API-Key": viewer_secret},
        )
        storage.save_instance_settings.assert_not_called()

    async def test_viewer_session_header_returns_403(self, auth_client_with_storage) -> None:
        """A session user with role=viewer (via X-User-* from trusted proxy) must be blocked."""
        from tests.security.conftest import _TEST_PROXY_SECRET, _sign_proxy_headers

        c, storage = auth_client_with_storage
        headers = _sign_proxy_headers("viewer-user-uuid", "viewer", _TEST_PROXY_SECRET)
        response = await c.put(
            "/api/settings",
            json={"redact_payloads": True},
            # Simulate trusted Next.js proxy injecting signed session headers
            headers=headers,
        )
        assert response.status_code == 403
        storage.save_instance_settings.assert_not_called()

    async def test_viewer_db_key_cannot_read_settings(self, viewer_client_with_storage) -> None:
        """GET /api/settings now requires admin role — viewer keys get 403.

        Updated security: both read and write require admin role.
        """
        c, _, viewer_secret = viewer_client_with_storage
        response = await c.get(
            "/api/settings",
            headers={"X-API-Key": viewer_secret},
        )
        assert response.status_code == 403


# ===========================================================================
# Class 4 — SSE project isolation: span:new events must not cross project boundaries
# ===========================================================================


class TestSSEProjectIsolation:
    """Invariant: SSEBroadcaster must not deliver project-B events to project-A subscribers.

    Old broken behaviour: when event_project was "" (payload had no project_id),
    the filter short-circuited and ALL project-scoped subscribers received the
    event. This test targets the fixed forward path: an event WITH a project_id
    must be filtered to only the matching project's subscribers.

    Additionally, the test proves the dual invariant:
      - project-A subscriber DOES receive project-A events (no over-filtering)
      - project-A subscriber does NOT receive project-B events (the regression)
    """

    async def test_project_b_event_not_delivered_to_project_a_subscriber(self) -> None:
        """span:new for project-B must not arrive in project-A's subscriber queue."""
        from langsight.api.broadcast import SSEBroadcaster

        broadcaster = SSEBroadcaster()

        project_a_received: list[str] = []

        async def drain_project_a(max_events: int = 5) -> None:
            count = 0
            async for chunk in broadcaster.subscribe(project_id="project-a"):
                if chunk.startswith(": connected"):
                    continue
                project_a_received.append(chunk)
                count += 1
                if count >= max_events:
                    break

        # Start subscriber for project-a
        subscriber_task = asyncio.create_task(drain_project_a())
        # Yield to let the subscriber register itself
        await asyncio.sleep(0)

        # Publish a span:new event for project-B only
        broadcaster.publish("span:new", {"project_id": "project-b", "span_id": "span-xyz"})
        # Give the event loop a moment to route the event
        await asyncio.sleep(0)

        subscriber_task.cancel()
        try:
            await subscriber_task
        except asyncio.CancelledError:
            pass

        assert project_a_received == [], (
            "Project-A subscriber received a project-B event — SSE isolation broken. "
            f"Received: {project_a_received}"
        )

    async def test_project_a_event_is_delivered_to_project_a_subscriber(self) -> None:
        """Positive control: project-A events must reach project-A subscriber.

        Ensures we did not over-filter (a regression in the other direction).
        """
        from langsight.api.broadcast import SSEBroadcaster

        broadcaster = SSEBroadcaster()

        project_a_received: list[str] = []

        async def drain_project_a() -> None:
            async for chunk in broadcaster.subscribe(project_id="project-a"):
                if chunk.startswith(": connected"):
                    continue
                project_a_received.append(chunk)
                return  # stop after first real event

        subscriber_task = asyncio.create_task(drain_project_a())
        await asyncio.sleep(0)

        broadcaster.publish("span:new", {"project_id": "project-a", "span_id": "span-abc"})
        await asyncio.sleep(0.05)

        subscriber_task.cancel()
        try:
            await subscriber_task
        except asyncio.CancelledError:
            pass

        assert len(project_a_received) >= 1, (
            "Project-A subscriber did NOT receive its own event — SSE filter is too aggressive."
        )
        assert "project-a" in project_a_received[0], (
            f"Event body does not contain project-a: {project_a_received[0]}"
        )

    async def test_no_project_id_in_payload_does_not_reach_project_scoped_subscriber(self) -> None:
        """Unscoped events (no project_id in payload) must NOT reach project-scoped subscribers.

        Security fix: previously the filter short-circuited when event_project=""
        and leaked unscoped events to all project subscribers. Now only admin
        (project_id=None) subscribers receive unscoped events.
        """
        from langsight.api.broadcast import SSEBroadcaster

        broadcaster = SSEBroadcaster()

        received: list[str] = []

        async def drain() -> None:
            async for chunk in broadcaster.subscribe(project_id="project-a"):
                if chunk.startswith(": connected"):
                    continue
                received.append(chunk)
                return

        task = asyncio.create_task(drain())
        await asyncio.sleep(0)

        # Publish with no project_id in the payload
        broadcaster.publish("health:check", {"server": "postgres-mcp", "status": "up"})
        await asyncio.sleep(0.05)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Project-scoped subscriber must NOT receive unscoped events
        assert len(received) == 0, (
            "Unscoped event (no project_id) leaked to project-scoped subscriber — "
            "cross-project SSE event isolation is broken."
        )

    async def test_admin_subscriber_receives_all_project_events(self) -> None:
        """Admin subscriber (project_id=None) must receive events from every project."""
        from langsight.api.broadcast import SSEBroadcaster

        broadcaster = SSEBroadcaster()

        admin_received: list[str] = []

        async def drain_admin() -> None:
            count = 0
            async for chunk in broadcaster.subscribe(project_id=None):
                if chunk.startswith(": connected"):
                    continue
                admin_received.append(chunk)
                count += 1
                if count >= 2:
                    return

        task = asyncio.create_task(drain_admin())
        await asyncio.sleep(0)

        broadcaster.publish("span:new", {"project_id": "project-a", "span_id": "a1"})
        broadcaster.publish("span:new", {"project_id": "project-b", "span_id": "b1"})
        await asyncio.sleep(0.05)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert len(admin_received) == 2, (
            f"Admin subscriber expected 2 events (one per project), got {len(admin_received)}."
        )

    async def test_cross_project_attack_with_known_project_ids(self) -> None:
        """Adversarial: attacker subscribes to project-A, publishes project-B events.

        Even if the attacker knows both project IDs, project-B events must not
        arrive in the project-A channel.
        """
        from langsight.api.broadcast import SSEBroadcaster

        broadcaster = SSEBroadcaster()

        attacker_received: list[str] = []

        async def attacker_subscriber() -> None:
            # Attacker subscribes as project-a (where they have legitimate access)
            async for chunk in broadcaster.subscribe(project_id="project-a"):
                if chunk.startswith(": connected"):
                    continue
                attacker_received.append(chunk)
                return

        task = asyncio.create_task(attacker_subscriber())
        await asyncio.sleep(0)

        # Victim's event — published for project-b only
        broadcaster.publish(
            "span:new",
            {
                "project_id": "project-b",
                "span_id": "victim-span",
                "payload": "sensitive-data",
            },
        )
        await asyncio.sleep(0.05)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert attacker_received == [], (
            "Cross-project attack succeeded: project-A subscriber received project-B event. "
            f"Intercepted events: {attacker_received}"
        )
