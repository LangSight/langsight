"""Unit tests for gen_ai.* attribute alignment in the OTLP ingest path.

Covers _parse_otlp_span() reading standard OpenTelemetry GenAI semantic
convention attributes introduced in the gen_ai.conversation.id alignment:

  session_id   ← attrs["session.id"]  OR  attrs["gen_ai.conversation.id"]
                 (session.id wins when both are present)
  agent_name   ← attrs["gen_ai.agent.name"]  OR  attrs["gen_ai.agent.id"]
                 (gen_ai.agent.name wins when both are present)
  cache_read_tokens     ← attrs["gen_ai.usage.cache_read_input_tokens"]
  cache_creation_tokens ← attrs["gen_ai.usage.cache_creation_input_tokens"]

Also verifies the full HTTP path: POSTing a span to /api/traces/otlp with
these attributes stores a ToolCallSpan with the expected field values.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from langsight.api.main import create_app
from langsight.config import load_config


# ---------------------------------------------------------------------------
# OTLP payload helpers  (mirrors patterns in test_traces_router.py)
# ---------------------------------------------------------------------------


def _attr(key: str, value: str | int) -> dict:
    """Build a single OTLP attribute dict."""
    if isinstance(value, int):
        return {"key": key, "value": {"intValue": value}}
    return {"key": key, "value": {"stringValue": value}}


def _otlp_span(
    name: str = "mcp.tool.call",
    attrs: list | None = None,
    start_ns: str = "1700000000000000000",
    end_ns: str = "1700000042000000000",
) -> dict:
    return {
        "name": name,
        "spanId": "abc123",
        "traceId": "trace001",
        "startTimeUnixNano": start_ns,
        "endTimeUnixNano": end_ns,
        "status": {"code": 1},
        "attributes": attrs or [],
    }


def _otlp_payload(spans: list) -> dict:
    return {
        "resourceSpans": [
            {
                "resource": {"attributes": []},
                "scopeSpans": [{"scope": {}, "spans": spans}],
            }
        ]
    }


# ---------------------------------------------------------------------------
# Direct _parse_otlp_span unit tests  (no HTTP, no app fixtures needed)
# ---------------------------------------------------------------------------


class TestParseOtlpSpanGenAiAlignment:
    """Direct unit tests for _parse_otlp_span — no HTTP stack required."""

    def _call(self, span: dict):
        from langsight.api.routers.traces import _parse_otlp_span

        return _parse_otlp_span(span)

    def test_session_id_from_gen_ai_conversation_id(self) -> None:
        """gen_ai.conversation.id is used as session_id when session.id is absent."""
        span = _otlp_span(attrs=[
            _attr("mcp.server.name", "pg"),
            _attr("mcp.tool.name", "query"),
            _attr("gen_ai.conversation.id", "conv-abc-123"),
        ])
        result = self._call(span)
        assert result is not None
        assert result.session_id == "conv-abc-123"

    def test_session_id_prefers_session_id_over_gen_ai(self) -> None:
        """session.id takes precedence over gen_ai.conversation.id when both present."""
        span = _otlp_span(attrs=[
            _attr("mcp.server.name", "pg"),
            _attr("mcp.tool.name", "query"),
            _attr("session.id", "session-primary"),
            _attr("gen_ai.conversation.id", "conv-should-be-ignored"),
        ])
        result = self._call(span)
        assert result is not None
        assert result.session_id == "session-primary"

    def test_session_id_none_when_neither_attr_present(self) -> None:
        """session_id is None when neither session.id nor gen_ai.conversation.id is set."""
        span = _otlp_span(attrs=[
            _attr("mcp.server.name", "pg"),
            _attr("mcp.tool.name", "query"),
        ])
        result = self._call(span)
        assert result is not None
        assert result.session_id is None

    def test_agent_name_from_gen_ai_agent_id(self) -> None:
        """gen_ai.agent.id is used as agent_name when gen_ai.agent.name is absent."""
        span = _otlp_span(attrs=[
            _attr("mcp.server.name", "pg"),
            _attr("mcp.tool.name", "query"),
            _attr("gen_ai.agent.id", "analyst"),
        ])
        result = self._call(span)
        assert result is not None
        assert result.agent_name == "analyst"

    def test_agent_name_prefers_gen_ai_agent_name_over_agent_id(self) -> None:
        """gen_ai.agent.name takes precedence over gen_ai.agent.id when both present."""
        span = _otlp_span(attrs=[
            _attr("mcp.server.name", "pg"),
            _attr("mcp.tool.name", "query"),
            _attr("gen_ai.agent.name", "orchestrator"),
            _attr("gen_ai.agent.id", "agent-id-ignored"),
        ])
        result = self._call(span)
        assert result is not None
        assert result.agent_name == "orchestrator"

    def test_agent_name_none_when_neither_attr_present(self) -> None:
        """agent_name is None when neither gen_ai.agent.name nor gen_ai.agent.id is set."""
        span = _otlp_span(attrs=[
            _attr("mcp.server.name", "pg"),
            _attr("mcp.tool.name", "query"),
        ])
        result = self._call(span)
        assert result is not None
        assert result.agent_name is None

    def test_cache_read_tokens_from_otlp(self) -> None:
        """gen_ai.usage.cache_read_input_tokens=200 → cache_read_tokens=200."""
        span = _otlp_span(attrs=[
            _attr("mcp.server.name", "pg"),
            _attr("mcp.tool.name", "query"),
            _attr("gen_ai.usage.cache_read_input_tokens", 200),
        ])
        result = self._call(span)
        assert result is not None
        assert result.cache_read_tokens == 200

    def test_cache_creation_tokens_from_otlp(self) -> None:
        """gen_ai.usage.cache_creation_input_tokens=50 → cache_creation_tokens=50."""
        span = _otlp_span(attrs=[
            _attr("mcp.server.name", "pg"),
            _attr("mcp.tool.name", "query"),
            _attr("gen_ai.usage.cache_creation_input_tokens", 50),
        ])
        result = self._call(span)
        assert result is not None
        assert result.cache_creation_tokens == 50

    def test_both_cache_token_attrs_parsed_together(self) -> None:
        """Both cache attributes can be read from the same span simultaneously."""
        span = _otlp_span(attrs=[
            _attr("mcp.server.name", "pg"),
            _attr("mcp.tool.name", "query"),
            _attr("gen_ai.usage.cache_read_input_tokens", 300),
            _attr("gen_ai.usage.cache_creation_input_tokens", 75),
        ])
        result = self._call(span)
        assert result is not None
        assert result.cache_read_tokens == 300
        assert result.cache_creation_tokens == 75

    def test_cache_tokens_default_none_when_absent(self) -> None:
        """Spans without cache token attrs produce None for both cache fields."""
        span = _otlp_span(attrs=[
            _attr("mcp.server.name", "pg"),
            _attr("mcp.tool.name", "query"),
            _attr("gen_ai.usage.input_tokens", 100),
            _attr("gen_ai.usage.output_tokens", 40),
        ])
        result = self._call(span)
        assert result is not None
        assert result.cache_read_tokens is None
        assert result.cache_creation_tokens is None

    def test_regular_tokens_unaffected_by_cache_tokens(self) -> None:
        """input_tokens and output_tokens are parsed correctly alongside cache tokens."""
        span = _otlp_span(attrs=[
            _attr("mcp.server.name", "pg"),
            _attr("mcp.tool.name", "query"),
            _attr("gen_ai.usage.input_tokens", 500),
            _attr("gen_ai.usage.output_tokens", 120),
            _attr("gen_ai.usage.cache_read_input_tokens", 200),
            _attr("gen_ai.usage.cache_creation_input_tokens", 30),
        ])
        result = self._call(span)
        assert result is not None
        assert result.input_tokens == 500
        assert result.output_tokens == 120
        assert result.cache_read_tokens == 200
        assert result.cache_creation_tokens == 30

    def test_all_gen_ai_alignment_attrs_together(self) -> None:
        """session_id, agent_name, and both cache fields are all read in one span."""
        span = _otlp_span(attrs=[
            _attr("mcp.server.name", "pg"),
            _attr("mcp.tool.name", "query"),
            _attr("gen_ai.conversation.id", "sess-xyz"),
            _attr("gen_ai.agent.id", "analyst"),
            _attr("gen_ai.usage.cache_read_input_tokens", 150),
            _attr("gen_ai.usage.cache_creation_input_tokens", 20),
        ])
        result = self._call(span)
        assert result is not None
        assert result.session_id == "sess-xyz"
        assert result.agent_name == "analyst"
        assert result.cache_read_tokens == 150
        assert result.cache_creation_tokens == 20


# ---------------------------------------------------------------------------
# HTTP integration path — POST /api/traces/otlp (mocked storage)
# ---------------------------------------------------------------------------


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(yaml.dump({"servers": [], "auth_disabled": True}))
    return cfg


@pytest.fixture
async def client(config_file: Path):
    app = create_app(config_path=config_file)
    mock_storage = MagicMock()
    mock_storage.save_tool_call_spans = AsyncMock()
    app.state.storage = mock_storage
    app.state.config = load_config(config_file)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


class TestOtlpIngestGenAiAlignment:
    """End-to-end path: POST /api/traces/otlp stores spans with correct gen_ai fields."""

    async def test_session_id_from_gen_ai_conversation_id(self, client, config_file) -> None:
        """Spans stored via OTLP ingest carry session_id from gen_ai.conversation.id."""
        span = _otlp_span(attrs=[
            _attr("mcp.server.name", "pg"),
            _attr("mcp.tool.name", "query"),
            _attr("gen_ai.conversation.id", "conv-http-test"),
        ])
        r = await client.post(
            "/api/traces/otlp",
            json=_otlp_payload([span]),
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 202
        assert r.json()["accepted"] == 1

        # Verify the span passed to storage has the expected session_id
        app = client._transport.app  # type: ignore[attr-defined]
        saved_spans = app.state.storage.save_tool_call_spans.call_args[0][0]
        assert saved_spans[0].session_id == "conv-http-test"

    async def test_session_id_prefers_session_id_over_gen_ai(self, client, config_file) -> None:
        """session.id wins over gen_ai.conversation.id in the stored span."""
        span = _otlp_span(attrs=[
            _attr("mcp.server.name", "pg"),
            _attr("mcp.tool.name", "query"),
            _attr("session.id", "sess-wins"),
            _attr("gen_ai.conversation.id", "conv-loses"),
        ])
        r = await client.post(
            "/api/traces/otlp",
            json=_otlp_payload([span]),
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 202

        app = client._transport.app  # type: ignore[attr-defined]
        saved_spans = app.state.storage.save_tool_call_spans.call_args[0][0]
        assert saved_spans[0].session_id == "sess-wins"

    async def test_agent_name_from_gen_ai_agent_id(self, client, config_file) -> None:
        """Stored span has agent_name from gen_ai.agent.id when gen_ai.agent.name absent."""
        span = _otlp_span(attrs=[
            _attr("mcp.server.name", "pg"),
            _attr("mcp.tool.name", "query"),
            _attr("gen_ai.agent.id", "analyst"),
        ])
        r = await client.post(
            "/api/traces/otlp",
            json=_otlp_payload([span]),
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 202

        app = client._transport.app  # type: ignore[attr-defined]
        saved_spans = app.state.storage.save_tool_call_spans.call_args[0][0]
        assert saved_spans[0].agent_name == "analyst"

    async def test_cache_read_tokens_from_otlp(self, client, config_file) -> None:
        """Stored span has cache_read_tokens=200 from gen_ai.usage.cache_read_input_tokens."""
        span = _otlp_span(attrs=[
            _attr("mcp.server.name", "pg"),
            _attr("mcp.tool.name", "query"),
            _attr("gen_ai.usage.cache_read_input_tokens", 200),
        ])
        r = await client.post(
            "/api/traces/otlp",
            json=_otlp_payload([span]),
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 202

        app = client._transport.app  # type: ignore[attr-defined]
        saved_spans = app.state.storage.save_tool_call_spans.call_args[0][0]
        assert saved_spans[0].cache_read_tokens == 200

    async def test_cache_creation_tokens_from_otlp(self, client, config_file) -> None:
        """Stored span has cache_creation_tokens=50 from gen_ai.usage.cache_creation_input_tokens."""
        span = _otlp_span(attrs=[
            _attr("mcp.server.name", "pg"),
            _attr("mcp.tool.name", "query"),
            _attr("gen_ai.usage.cache_creation_input_tokens", 50),
        ])
        r = await client.post(
            "/api/traces/otlp",
            json=_otlp_payload([span]),
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 202

        app = client._transport.app  # type: ignore[attr-defined]
        saved_spans = app.state.storage.save_tool_call_spans.call_args[0][0]
        assert saved_spans[0].cache_creation_tokens == 50
