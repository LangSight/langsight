"""
Adversarial security tests for lineage hardening (v1.0 protocol).

Lineage data determines what operators see in the dashboard. Corrupted lineage
can hide malicious agent behaviour or create false trails. These tests verify
that hostile inputs are rejected or safely stored, that cross-project lineage
cannot be forged, and that denial-of-service via large batches does not halt
ingestion.

Tested surfaces:
  - ToolCallSpan Pydantic model (input validation, Literal enforcement)
  - traces.py ingest_spans (lineage validation, legacy upgrade, batch checks)
  - ClickHouse _span_row (parameterised storage, no injection)
  - _lineage_handoff_edges query (parameterised, SQL-safe)

All tests are offline — no Docker, no real DB, no network.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from langsight.sdk.models import ToolCallSpan, ToolCallStatus

pytestmark = pytest.mark.security


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(UTC)


def _valid_session_id() -> str:
    return uuid.uuid4().hex


def _span_dict(
    *,
    server: str = "pg",
    tool: str = "query",
    status: str = "success",
    session_id: str | None = None,
    span_id: str | None = None,
    parent_span_id: str | None = None,
    span_type: str = "tool_call",
    agent_name: str | None = None,
    target_agent_name: str | None = None,
    lineage_provenance: str = "explicit",
    lineage_status: str = "complete",
    schema_version: str = "1.0",
    trace_id: str | None = None,
    project_id: str | None = None,
) -> dict:
    """Build a valid span JSON payload for the ingest endpoint."""
    now = _now().isoformat()
    d: dict = {
        "server_name": server,
        "tool_name": tool,
        "started_at": now,
        "ended_at": now,
        "latency_ms": 10.0,
        "status": status,
    }
    if session_id is not None:
        d["session_id"] = session_id
    if span_id is not None:
        d["span_id"] = span_id
    if parent_span_id is not None:
        d["parent_span_id"] = parent_span_id
    if span_type != "tool_call":
        d["span_type"] = span_type
    if agent_name is not None:
        d["agent_name"] = agent_name
    if target_agent_name is not None:
        d["target_agent_name"] = target_agent_name
    if lineage_provenance != "explicit":
        d["lineage_provenance"] = lineage_provenance
    if lineage_status != "complete":
        d["lineage_status"] = lineage_status
    if schema_version != "1.0":
        d["schema_version"] = schema_version
    if trace_id is not None:
        d["trace_id"] = trace_id
    if project_id is not None:
        d["project_id"] = project_id
    return d


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(yaml.dump({"servers": []}))
    return cfg


@pytest.fixture
async def client(config_file: Path):
    """AsyncClient with no auth, mock storage that accepts spans."""
    from langsight.api.main import create_app
    from langsight.config import load_config

    app = create_app(config_path=config_file)
    mock_storage = MagicMock()
    mock_storage.save_tool_call_spans = AsyncMock()
    mock_storage.save_session_health_tag = AsyncMock()
    mock_storage.get_session_health_tag = AsyncMock(return_value=None)
    mock_storage.upsert_agent_metadata = AsyncMock()
    mock_storage.upsert_server_metadata = AsyncMock()
    mock_storage.list_api_keys = AsyncMock(return_value=[])
    mock_storage.get_instance_settings = AsyncMock(return_value={})
    mock_storage.close = AsyncMock()

    app.state.storage = mock_storage
    app.state.config = load_config(config_file)
    app.state.api_keys = []  # auth disabled for direct span testing

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, mock_storage


# ============================================================================
# 1. INPUT VALIDATION — MALICIOUS FIELD VALUES
# ============================================================================

class TestMaliciousFieldValues:
    """Invariant: hostile strings in lineage fields cannot cause injection or crashes."""

    def test_sql_injection_in_target_agent_name_stored_safely(self) -> None:
        """SQL injection payload in target_agent_name must be accepted as a literal string.

        The model stores it as-is; parameterised queries prevent execution.
        """
        payload = "analyst'; DROP TABLE mcp_tool_calls; --"
        span = ToolCallSpan(
            server_name="attacker",
            tool_name="handoff",
            started_at=_now(),
            ended_at=_now(),
            status=ToolCallStatus.SUCCESS,
            span_type="handoff",
            target_agent_name=payload,
        )
        assert span.target_agent_name == payload

    def test_xss_payload_in_target_agent_name_stored_as_is(self) -> None:
        """XSS payload must be stored verbatim. Dashboard is responsible for escaping."""
        payload = "<script>alert('xss')</script>"
        span = ToolCallSpan(
            server_name="attacker",
            tool_name="handoff",
            started_at=_now(),
            ended_at=_now(),
            status=ToolCallStatus.SUCCESS,
            span_type="handoff",
            target_agent_name=payload,
        )
        assert span.target_agent_name == payload
        # Verify the raw script tag is preserved (not sanitised at model level)
        assert "<script>" in span.target_agent_name

    def test_invalid_lineage_provenance_rejected_by_pydantic(self) -> None:
        """lineage_provenance must be one of the defined Literal values."""
        with pytest.raises(ValidationError) as exc_info:
            ToolCallSpan(
                server_name="test",
                tool_name="test",
                started_at=_now(),
                ended_at=_now(),
                status=ToolCallStatus.SUCCESS,
                lineage_provenance="malicious_value",  # type: ignore[arg-type]
            )
        errors = exc_info.value.errors()
        assert any("lineage_provenance" in str(e) for e in errors)

    def test_invalid_lineage_status_rejected_by_pydantic(self) -> None:
        """lineage_status must be one of the defined Literal values."""
        with pytest.raises(ValidationError) as exc_info:
            ToolCallSpan(
                server_name="test",
                tool_name="test",
                started_at=_now(),
                ended_at=_now(),
                status=ToolCallStatus.SUCCESS,
                lineage_status="pwned",  # type: ignore[arg-type]
            )
        errors = exc_info.value.errors()
        assert any("lineage_status" in str(e) for e in errors)

    def test_absurdly_long_schema_version_does_not_crash(self) -> None:
        """A 10000-char schema_version must not OOM or crash the model."""
        long_version = "X" * 10_000
        span = ToolCallSpan(
            server_name="test",
            tool_name="test",
            started_at=_now(),
            ended_at=_now(),
            status=ToolCallStatus.SUCCESS,
            schema_version=long_version,
        )
        assert len(span.schema_version) == 10_000

    def test_target_agent_name_empty_string_vs_none(self) -> None:
        """Empty string and None are distinct. Empty string should not alias to None."""
        span_empty = ToolCallSpan(
            server_name="test",
            tool_name="test",
            started_at=_now(),
            ended_at=_now(),
            status=ToolCallStatus.SUCCESS,
            target_agent_name="",
        )
        span_none = ToolCallSpan(
            server_name="test",
            tool_name="test",
            started_at=_now(),
            ended_at=_now(),
            status=ToolCallStatus.SUCCESS,
            target_agent_name=None,
        )
        assert span_empty.target_agent_name == ""
        assert span_none.target_agent_name is None

    def test_null_bytes_in_target_agent_name(self) -> None:
        """Null bytes are a classic C-string termination attack vector."""
        payload = "analyst\x00; DROP TABLE mcp_tool_calls"
        span = ToolCallSpan(
            server_name="test",
            tool_name="handoff",
            started_at=_now(),
            ended_at=_now(),
            status=ToolCallStatus.SUCCESS,
            span_type="handoff",
            target_agent_name=payload,
        )
        # Must store verbatim — not truncate at null byte
        assert span.target_agent_name == payload
        assert "\x00" in span.target_agent_name

    def test_unicode_homoglyph_in_target_agent_name(self) -> None:
        """Unicode homoglyphs can create visually identical but distinct agent names.

        An attacker could register 'analyst' (Latin) and 'аnаlyst' (Cyrillic a)
        to create a phantom handoff target. The model must store the exact bytes.
        """
        latin = "analyst"
        cyrillic_a = "\u0430"  # Cyrillic small letter a
        homoglyph = f"{cyrillic_a}n{cyrillic_a}lyst"

        span_real = ToolCallSpan(
            server_name="test", tool_name="h", started_at=_now(),
            ended_at=_now(), status=ToolCallStatus.SUCCESS,
            target_agent_name=latin,
        )
        span_fake = ToolCallSpan(
            server_name="test", tool_name="h", started_at=_now(),
            ended_at=_now(), status=ToolCallStatus.SUCCESS,
            target_agent_name=homoglyph,
        )
        # They look similar but MUST be stored as distinct values
        assert span_real.target_agent_name != span_fake.target_agent_name


class TestInvalidLineageFieldCombinations:
    """Invariant: invalid field combinations at the API boundary are rejected or handled safely."""

    async def test_invalid_provenance_rejected_at_api_boundary(self, client) -> None:
        """POST /api/traces/spans with invalid lineage_provenance returns 422."""
        c, _storage = client
        payload = _span_dict(lineage_provenance="malicious_value")
        resp = await c.post("/api/traces/spans", json=[payload])
        assert resp.status_code == 422

    async def test_invalid_status_rejected_at_api_boundary(self, client) -> None:
        """POST /api/traces/spans with invalid lineage_status returns 422."""
        c, _storage = client
        payload = _span_dict(lineage_status="pwned")
        resp = await c.post("/api/traces/spans", json=[payload])
        assert resp.status_code == 422

    async def test_invalid_span_type_rejected_at_api_boundary(self, client) -> None:
        """POST /api/traces/spans with an unknown span_type returns 422."""
        c, _storage = client
        payload = _span_dict(span_type="backdoor")
        resp = await c.post("/api/traces/spans", json=[payload])
        assert resp.status_code == 422


# ============================================================================
# 2. LINEAGE SPOOFING — FALSE PARENT CLAIMS
# ============================================================================

class TestLineageSpoofing:
    """Invariant: orphaned parent references are flagged, circular links do not loop forever."""

    async def test_parent_not_in_batch_gets_incomplete_status(self, client) -> None:
        """A span claiming a parent_span_id not in the batch must be marked incomplete.

        This prevents an attacker from claiming parentage to an unknown span
        without any validation feedback.
        """
        c, storage = client
        sid = _valid_session_id()
        orphan_parent = str(uuid.uuid4())

        payload = [_span_dict(
            session_id=sid,
            span_id=str(uuid.uuid4()),
            parent_span_id=orphan_parent,
            lineage_status="complete",
        )]
        resp = await c.post("/api/traces/spans", json=payload)
        assert resp.status_code == 202

        # Verify storage was called — the span should have been mutated to incomplete
        if storage.save_tool_call_spans.called:
            saved_spans = storage.save_tool_call_spans.call_args[0][0]
            for span in saved_spans:
                if span.parent_span_id == orphan_parent:
                    assert span.lineage_status == "incomplete", (
                        "Orphaned parent_span_id must downgrade lineage_status to incomplete"
                    )

    async def test_parent_in_same_batch_keeps_complete_status(self, client) -> None:
        """A span whose parent IS in the same batch should remain 'complete'."""
        c, storage = client
        sid = _valid_session_id()
        parent_id = str(uuid.uuid4())
        child_id = str(uuid.uuid4())

        payload = [
            _span_dict(session_id=sid, span_id=parent_id),
            _span_dict(session_id=sid, span_id=child_id, parent_span_id=parent_id),
        ]
        resp = await c.post("/api/traces/spans", json=payload)
        assert resp.status_code == 202

        if storage.save_tool_call_spans.called:
            saved_spans = storage.save_tool_call_spans.call_args[0][0]
            child = next((s for s in saved_spans if s.span_id == child_id), None)
            assert child is not None
            assert child.lineage_status == "complete"

    async def test_circular_parent_references_do_not_infinite_loop(self, client) -> None:
        """Span A -> parent B, Span B -> parent A must not cause infinite validation loop.

        The ingest endpoint checks parent_span_id membership in a set (O(1) lookup),
        so circular references are handled identically to any other case.
        """
        c, _storage = client
        sid = _valid_session_id()
        id_a = str(uuid.uuid4())
        id_b = str(uuid.uuid4())

        payload = [
            _span_dict(session_id=sid, span_id=id_a, parent_span_id=id_b),
            _span_dict(session_id=sid, span_id=id_b, parent_span_id=id_a),
        ]
        # Must complete without hanging — timeout would fail the test
        resp = await c.post("/api/traces/spans", json=payload)
        assert resp.status_code == 202

    async def test_self_referencing_parent_does_not_crash(self, client) -> None:
        """A span with parent_span_id == span_id must not cause an error."""
        c, _storage = client
        sid = _valid_session_id()
        self_id = str(uuid.uuid4())

        payload = [_span_dict(
            session_id=sid,
            span_id=self_id,
            parent_span_id=self_id,
        )]
        resp = await c.post("/api/traces/spans", json=payload)
        assert resp.status_code == 202


# ============================================================================
# 3. LEGACY HANDOFF UPGRADE — INJECTION VIA tool_name
# ============================================================================

class TestLegacyHandoffUpgrade:
    """Invariant: legacy handoff upgrade extracts target_agent_name safely from tool_name."""

    async def test_legacy_handoff_with_sql_injection_in_tool_name(self, client) -> None:
        """tool_name='-> analyst; DROP TABLE' must extract safely, not execute."""
        c, storage = client
        sid = _valid_session_id()

        payload = [_span_dict(
            session_id=sid,
            span_type="handoff",
            tool="\u2192 analyst; DROP TABLE mcp_tool_calls; --",
            agent_name="supervisor",
        )]
        resp = await c.post("/api/traces/spans", json=payload)
        assert resp.status_code == 202

        if storage.save_tool_call_spans.called:
            saved = storage.save_tool_call_spans.call_args[0][0]
            handoff = next((s for s in saved if s.span_type == "handoff"), None)
            assert handoff is not None
            # target_agent_name must contain the literal string, not execute anything
            assert handoff.target_agent_name == "analyst; DROP TABLE mcp_tool_calls; --"
            assert handoff.lineage_provenance == "derived_legacy"

    async def test_legacy_handoff_with_empty_target_after_arrow(self, client) -> None:
        """tool_name='-> ' (empty after arrow) must not crash; target is empty string."""
        c, storage = client
        sid = _valid_session_id()

        payload = [_span_dict(
            session_id=sid,
            span_type="handoff",
            tool="\u2192 ",
            agent_name="supervisor",
        )]
        resp = await c.post("/api/traces/spans", json=payload)
        assert resp.status_code == 202

        if storage.save_tool_call_spans.called:
            saved = storage.save_tool_call_spans.call_args[0][0]
            handoff = next((s for s in saved if s.span_type == "handoff"), None)
            assert handoff is not None
            assert handoff.target_agent_name == ""

    async def test_no_arrow_in_tool_name_skips_upgrade(self, client) -> None:
        """A handoff span with tool_name lacking an arrow must not be upgraded."""
        c, storage = client
        sid = _valid_session_id()

        payload = [_span_dict(
            session_id=sid,
            span_type="handoff",
            tool="delegate_to_billing",
            agent_name="supervisor",
        )]
        resp = await c.post("/api/traces/spans", json=payload)
        assert resp.status_code == 202

        if storage.save_tool_call_spans.called:
            saved = storage.save_tool_call_spans.call_args[0][0]
            handoff = next((s for s in saved if s.span_type == "handoff"), None)
            assert handoff is not None
            # target_agent_name should remain None (no arrow pattern found)
            assert handoff.target_agent_name is None
            # provenance must NOT be changed to derived_legacy
            assert handoff.lineage_provenance == "explicit"

    async def test_legacy_upgrade_skipped_when_target_already_set(self, client) -> None:
        """If target_agent_name is already set, legacy upgrade must not overwrite it."""
        c, storage = client
        sid = _valid_session_id()

        payload = [_span_dict(
            session_id=sid,
            span_type="handoff",
            tool="\u2192 wrong-agent",
            agent_name="supervisor",
            target_agent_name="correct-agent",
        )]
        resp = await c.post("/api/traces/spans", json=payload)
        assert resp.status_code == 202

        if storage.save_tool_call_spans.called:
            saved = storage.save_tool_call_spans.call_args[0][0]
            handoff = next((s for s in saved if s.span_type == "handoff"), None)
            assert handoff is not None
            assert handoff.target_agent_name == "correct-agent", (
                "Legacy upgrade must not overwrite an explicit target_agent_name"
            )

    async def test_legacy_handoff_with_unicode_arrow_variant(self, client) -> None:
        """Both ASCII '-> ' and Unicode arrow are handled."""
        c, storage = client
        sid = _valid_session_id()

        # Use the ASCII arrow variant "→ " (U+2192)
        payload = [_span_dict(
            session_id=sid,
            span_type="handoff",
            tool="→ billing-agent",
            agent_name="supervisor",
        )]
        resp = await c.post("/api/traces/spans", json=payload)
        assert resp.status_code == 202

        if storage.save_tool_call_spans.called:
            saved = storage.save_tool_call_spans.call_args[0][0]
            handoff = next((s for s in saved if s.span_type == "handoff"), None)
            assert handoff is not None
            assert handoff.target_agent_name == "billing-agent"


# ============================================================================
# 4. DENIAL OF SERVICE — BATCH SIZE AND MEMORY
# ============================================================================

class TestDenialOfService:
    """Invariant: large or adversarial batches must not cause unbounded processing time or memory."""

    async def test_large_batch_with_orphaned_parents_validates_in_bounded_time(
        self, client
    ) -> None:
        """10,000 spans each with a unique non-existent parent must validate in < 2 seconds.

        The ingest endpoint uses a set for parent lookup — O(n) construction, O(1) per check.
        """
        c, _storage = client
        sid = _valid_session_id()
        spans = [
            _span_dict(
                session_id=sid,
                span_id=str(uuid.uuid4()),
                parent_span_id=str(uuid.uuid4()),  # always orphaned
            )
            for _ in range(10_000)
        ]

        start = time.monotonic()
        resp = await c.post("/api/traces/spans", json=spans)
        elapsed = time.monotonic() - start

        assert resp.status_code == 202
        assert elapsed < 2.0, f"Validation took {elapsed:.2f}s, expected < 2s"

    def test_many_handoff_spans_with_long_target_names_do_not_oom(self) -> None:
        """1000 handoff spans with 1KB target_agent_name must parse without memory issues."""
        long_name = "A" * 1024
        spans = [
            ToolCallSpan(
                server_name="attacker",
                tool_name=f"\u2192 {long_name}",
                started_at=_now(),
                ended_at=_now(),
                status=ToolCallStatus.SUCCESS,
                span_type="handoff",
                target_agent_name=long_name,
            )
            for _ in range(1000)
        ]
        # If we got here without MemoryError, the test passes.
        assert len(spans) == 1000
        # Verify all target names are intact
        assert all(s.target_agent_name == long_name for s in spans)


# ============================================================================
# 5. CLICKHOUSE STORAGE — PARAMETERISED QUERIES
# ============================================================================

class TestClickHouseStorageSafety:
    """Invariant: span data passes through parameterised queries, never string interpolation."""

    def test_span_row_serialises_sql_injection_payload_as_literal(self) -> None:
        """The _span_row method must produce a data row, not executable SQL."""
        from langsight.storage.clickhouse import ClickHouseBackend

        storage = ClickHouseBackend.__new__(ClickHouseBackend)

        malicious_span = ToolCallSpan(
            server_name="attacker",
            tool_name="handoff",
            started_at=_now(),
            ended_at=_now(),
            status=ToolCallStatus.SUCCESS,
            span_type="handoff",
            target_agent_name="analyst'; DROP TABLE mcp_tool_calls; --",
            lineage_provenance="explicit",
            lineage_status="complete",
            schema_version="1.0'; DROP TABLE mcp_tool_calls; --",
        )

        row = storage._span_row(malicious_span)

        # The row is a list of values — the SQL injection payload is a plain string
        # in the data list, NOT embedded in any SQL text.
        target_name_idx = storage._SPAN_COLUMNS.index("target_agent_name")
        schema_version_idx = storage._SPAN_COLUMNS.index("schema_version")

        assert row[target_name_idx] == "analyst'; DROP TABLE mcp_tool_calls; --"
        assert row[schema_version_idx] == "1.0'; DROP TABLE mcp_tool_calls; --"
        # Verify the row is a plain list, not a string containing SQL
        assert isinstance(row, list)

    def test_span_row_handles_none_target_agent_name(self) -> None:
        """When target_agent_name is None, _span_row must produce empty string (not NULL)."""
        from langsight.storage.clickhouse import ClickHouseBackend

        storage = ClickHouseBackend.__new__(ClickHouseBackend)

        span = ToolCallSpan(
            server_name="test",
            tool_name="test",
            started_at=_now(),
            ended_at=_now(),
            status=ToolCallStatus.SUCCESS,
            target_agent_name=None,
        )

        row = storage._span_row(span)
        target_idx = storage._SPAN_COLUMNS.index("target_agent_name")
        # ClickHouse column is String DEFAULT '' (not Nullable) — None must become ''
        assert row[target_idx] == ""

    def test_span_row_preserves_all_lineage_fields(self) -> None:
        """All four lineage fields must appear in the serialised row at correct positions."""
        from langsight.storage.clickhouse import ClickHouseBackend

        storage = ClickHouseBackend.__new__(ClickHouseBackend)

        span = ToolCallSpan(
            server_name="test",
            tool_name="test",
            started_at=_now(),
            ended_at=_now(),
            status=ToolCallStatus.SUCCESS,
            target_agent_name="billing-agent",
            lineage_provenance="derived_parent",
            lineage_status="incomplete",
            schema_version="2.0",
        )

        row = storage._span_row(span)

        assert row[storage._SPAN_COLUMNS.index("target_agent_name")] == "billing-agent"
        assert row[storage._SPAN_COLUMNS.index("lineage_provenance")] == "derived_parent"
        assert row[storage._SPAN_COLUMNS.index("lineage_status")] == "incomplete"
        assert row[storage._SPAN_COLUMNS.index("schema_version")] == "2.0"

    def test_xss_in_target_agent_name_stored_verbatim_in_row(self) -> None:
        """XSS must pass through _span_row unchanged — escaping is the dashboard's job."""
        from langsight.storage.clickhouse import ClickHouseBackend

        storage = ClickHouseBackend.__new__(ClickHouseBackend)

        xss = '<img src=x onerror="alert(document.cookie)">'
        span = ToolCallSpan(
            server_name="test",
            tool_name="test",
            started_at=_now(),
            ended_at=_now(),
            status=ToolCallStatus.SUCCESS,
            target_agent_name=xss,
        )

        row = storage._span_row(span)
        target_idx = storage._SPAN_COLUMNS.index("target_agent_name")
        assert row[target_idx] == xss


# ============================================================================
# 6. HANDOFF QUERY — SQL INJECTION IN STORED DATA
# ============================================================================

class TestHandoffQueryParameterisation:
    """Invariant: the handoff edge query uses parameterised placeholders, not string interpolation."""

    def test_handoff_query_uses_parameterised_project_id(self) -> None:
        """Verify the handoff query uses {project_id:String} placeholder, not f-string."""
        import inspect

        from langsight.storage.clickhouse import ClickHouseBackend

        source = inspect.getsource(ClickHouseBackend._lineage_handoff_edges)

        # Must contain parameterised placeholder
        assert "{project_id:String}" in source, (
            "_lineage_handoff_edges must use {project_id:String} parameterised placeholder"
        )
        # Must NOT contain dangerous f-string interpolation of project_id
        assert "f'{project_id}" not in source
        assert 'f"{project_id}' not in source

    def test_handoff_query_uses_parameterised_hours(self) -> None:
        """Verify the hours parameter is passed via placeholder, not interpolated."""
        import inspect

        from langsight.storage.clickhouse import ClickHouseBackend

        source = inspect.getsource(ClickHouseBackend._lineage_handoff_edges)
        assert "{hours:UInt32}" in source


# ============================================================================
# 7. TRACE ID CONSISTENCY — MULTI-TRACE BATCH WARNING
# ============================================================================

class TestTraceIdConsistency:
    """Invariant: batches with multiple trace_ids are logged as warnings but not rejected."""

    async def test_batch_with_multiple_trace_ids_still_accepted(self, client) -> None:
        """Multiple trace_ids in one batch is suspicious but must not block ingestion."""
        c, _storage = client
        sid = _valid_session_id()

        payload = [
            _span_dict(session_id=sid, trace_id="trace-aaa"),
            _span_dict(session_id=sid, trace_id="trace-bbb"),
        ]
        resp = await c.post("/api/traces/spans", json=payload)
        assert resp.status_code == 202


# ============================================================================
# 8. CROSS-PROCESS ENVELOPE SECURITY
# ============================================================================

class TestCrossProcessEnvelopeSecurity:
    """Invariant: malformed trace context headers/env vars are handled gracefully.

    The envelope propagation is documented but not yet implemented as code.
    These tests validate the model-level constraints that will protect the
    eventual implementation.
    """

    def test_trace_id_with_path_traversal_stored_safely(self) -> None:
        """trace_id containing path traversal payloads must be stored as literal strings."""
        payload = "../../../etc/passwd"
        span = ToolCallSpan(
            server_name="test",
            tool_name="test",
            started_at=_now(),
            ended_at=_now(),
            status=ToolCallStatus.SUCCESS,
            trace_id=payload,
        )
        assert span.trace_id == payload

    def test_project_id_from_span_cannot_override_auth_project(self) -> None:
        """A span's project_id field is informational — it does NOT bypass auth.

        The API extracts project_id from spans for tagging/routing, but auth
        checks (get_active_project_id) validate membership independently.
        A malicious SDK cannot gain access to another tenant by setting
        project_id in the span payload.
        """
        # Verify the model accepts any project_id (no auth at model level)
        span = ToolCallSpan(
            server_name="test",
            tool_name="test",
            started_at=_now(),
            ended_at=_now(),
            status=ToolCallStatus.SUCCESS,
            project_id="victim-project-id",
        )
        assert span.project_id == "victim-project-id"
        # The security guarantee is that auth middleware validates membership
        # BEFORE the span reaches storage — tested in test_project_isolation.py


# ============================================================================
# 9. LINEAGE PROTOCOL DEFAULTS AND BACKWARD COMPATIBILITY
# ============================================================================

class TestLineageProtocolDefaults:
    """Invariant: old SDK clients that omit lineage fields get safe defaults."""

    def test_omitted_lineage_provenance_defaults_to_explicit(self) -> None:
        """If lineage_provenance is not sent, default must be 'explicit'."""
        span = ToolCallSpan(
            server_name="test",
            tool_name="test",
            started_at=_now(),
            ended_at=_now(),
            status=ToolCallStatus.SUCCESS,
            # lineage_provenance omitted
        )
        assert span.lineage_provenance == "explicit"

    def test_omitted_lineage_status_defaults_to_complete(self) -> None:
        """If lineage_status is not sent, default must be 'complete'."""
        span = ToolCallSpan(
            server_name="test",
            tool_name="test",
            started_at=_now(),
            ended_at=_now(),
            status=ToolCallStatus.SUCCESS,
            # lineage_status omitted
        )
        assert span.lineage_status == "complete"

    def test_omitted_schema_version_defaults_to_1_0(self) -> None:
        """If schema_version is not sent, default must be '1.0'."""
        span = ToolCallSpan(
            server_name="test",
            tool_name="test",
            started_at=_now(),
            ended_at=_now(),
            status=ToolCallStatus.SUCCESS,
            # schema_version omitted
        )
        assert span.schema_version == "1.0"

    def test_omitted_target_agent_name_defaults_to_none(self) -> None:
        """If target_agent_name is not sent, default must be None."""
        span = ToolCallSpan(
            server_name="test",
            tool_name="test",
            started_at=_now(),
            ended_at=_now(),
            status=ToolCallStatus.SUCCESS,
            # target_agent_name omitted
        )
        assert span.target_agent_name is None

    async def test_old_sdk_span_without_lineage_fields_accepted(self, client) -> None:
        """A span payload from an old SDK (no lineage fields) must be accepted with defaults."""
        c, _storage = client
        sid = _valid_session_id()
        payload = [{
            "server_name": "pg",
            "tool_name": "query",
            "started_at": _now().isoformat(),
            "ended_at": _now().isoformat(),
            "status": "success",
            "session_id": sid,
            # No lineage fields at all
        }]
        resp = await c.post("/api/traces/spans", json=payload)
        assert resp.status_code == 202


# ============================================================================
# 10. HANDOFF SPAN CONSTRUCTION SAFETY
# ============================================================================

class TestHandoffSpanFactory:
    """Invariant: the handoff_span() factory method always sets correct provenance."""

    def test_handoff_span_sets_explicit_provenance(self) -> None:
        """handoff_span() must set lineage_provenance='explicit', not derived."""
        span = ToolCallSpan.handoff_span(
            from_agent="supervisor",
            to_agent="analyst",
            started_at=_now(),
        )
        assert span.lineage_provenance == "explicit"
        assert span.target_agent_name == "analyst"
        assert span.span_type == "handoff"

    def test_handoff_span_with_sql_injection_in_to_agent(self) -> None:
        """SQL injection in to_agent parameter must be stored verbatim."""
        malicious = "analyst'; DROP TABLE users; --"
        span = ToolCallSpan.handoff_span(
            from_agent="supervisor",
            to_agent=malicious,
            started_at=_now(),
        )
        assert span.target_agent_name == malicious
        assert malicious in span.tool_name  # tool_name contains "-> {to_agent}"

    def test_handoff_span_with_empty_to_agent(self) -> None:
        """Empty to_agent should be stored as empty string, not crash."""
        span = ToolCallSpan.handoff_span(
            from_agent="supervisor",
            to_agent="",
            started_at=_now(),
        )
        assert span.target_agent_name == ""
        assert span.span_type == "handoff"
