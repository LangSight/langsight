from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from langsight.api.main import create_app
from langsight.config import load_config


def _span_payload(
    server: str = "pg",
    tool: str = "query",
    status: str = "success",
) -> dict:
    now = datetime.now(UTC).isoformat()
    return {
        "server_name": server,
        "tool_name": tool,
        "started_at": now,
        "ended_at": now,
        "latency_ms": 42.0,
        "status": status,
    }


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / ".langsight.yaml"
    cfg.write_text(yaml.dump({"servers": []}))
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


class TestTracesEndpoint:
    async def test_returns_202_accepted(self, client) -> None:
        response = await client.post(
            "/api/traces/spans",
            json=[_span_payload()],
        )
        assert response.status_code == 202

    async def test_returns_accepted_count(self, client) -> None:
        spans = [_span_payload(), _span_payload(tool="list_tables")]
        data = (await client.post("/api/traces/spans", json=spans)).json()
        assert data["accepted"] == 2

    async def test_accepts_empty_list(self, client) -> None:
        response = await client.post("/api/traces/spans", json=[])
        assert response.status_code == 202
        assert response.json()["accepted"] == 0

    async def test_accepts_error_span(self, client) -> None:
        payload = _span_payload(status="error")
        payload["error"] = "connection refused"
        response = await client.post("/api/traces/spans", json=[payload])
        assert response.status_code == 202

    async def test_accepts_timeout_span(self, client) -> None:
        payload = _span_payload(status="timeout")
        response = await client.post("/api/traces/spans", json=[payload])
        assert response.status_code == 202

    async def test_rejects_invalid_status(self, client) -> None:
        payload = _span_payload(status="unknown_status")
        response = await client.post("/api/traces/spans", json=[payload])
        assert response.status_code == 422

    async def test_accepts_span_with_all_metadata(self, client) -> None:
        payload = _span_payload()
        payload.update({
            "trace_id": "trace-123",
            "agent_name": "support-agent",
            "session_id": "sess-abc",
        })
        response = await client.post("/api/traces/spans", json=[payload])
        assert response.status_code == 202


# ---------------------------------------------------------------------------
# OTLP ingest endpoint + _parse_otlp_span helper
# ---------------------------------------------------------------------------

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
    return {"resourceSpans": [{"resource": {"attributes": []},
            "scopeSpans": [{"scope": {}, "spans": spans}]}]}


class TestOTLPIngest:
    async def test_accepts_mcp_span(self, client) -> None:
        span = _otlp_span(attrs=[
            {"key": "mcp.server.name", "value": {"stringValue": "pg"}},
            {"key": "mcp.tool.name", "value": {"stringValue": "query"}},
        ])
        r = await client.post("/api/traces/otlp", json=_otlp_payload([span]),
                              headers={"Content-Type": "application/json"})
        assert r.status_code == 202

    async def test_accepts_empty_otlp(self, client) -> None:
        r = await client.post("/api/traces/otlp", json={"resourceSpans": []},
                              headers={"Content-Type": "application/json"})
        assert r.status_code == 202
        assert r.json()["accepted"] == 0

    async def test_ignores_non_mcp_span(self, client) -> None:
        span = _otlp_span(name="http.request", attrs=[
            {"key": "http.method", "value": {"stringValue": "GET"}},
        ])
        r = await client.post("/api/traces/otlp", json=_otlp_payload([span]),
                              headers={"Content-Type": "application/json"})
        assert r.status_code == 202
        assert r.json()["accepted"] == 0


class TestParseOtlpSpan:
    def _call(self, span: dict):
        from langsight.api.routers.traces import _parse_otlp_span
        return _parse_otlp_span(span)

    def test_returns_none_for_non_mcp(self) -> None:
        assert self._call(_otlp_span(name="grpc.call", attrs=[
            {"key": "rpc.method", "value": {"stringValue": "Invoke"}}
        ])) is None

    def test_parses_mcp_attrs(self) -> None:
        r = self._call(_otlp_span(attrs=[
            {"key": "mcp.server.name", "value": {"stringValue": "my-srv"}},
            {"key": "mcp.tool.name", "value": {"stringValue": "my-tool"}},
        ]))
        assert r is not None
        assert r.server_name == "my-srv"
        assert r.tool_name == "my-tool"

    def test_parses_gen_ai_tool(self) -> None:
        r = self._call(_otlp_span(name="gen_ai.tool.execute", attrs=[
            {"key": "gen_ai.tool.name", "value": {"stringValue": "search"}},
        ]))
        assert r is not None
        assert r.tool_name == "search"

    def test_parses_int_tokens(self) -> None:
        r = self._call(_otlp_span(attrs=[
            {"key": "mcp.server.name", "value": {"stringValue": "s"}},
            {"key": "mcp.tool.name", "value": {"stringValue": "t"}},
            {"key": "gen_ai.usage.input_tokens", "value": {"intValue": 42}},
            {"key": "gen_ai.usage.output_tokens", "value": {"intValue": 10}},
        ]))
        assert r is not None
        assert r.input_tokens == 42
        assert r.output_tokens == 10

    def test_parses_llm_span(self) -> None:
        r = self._call(_otlp_span(name="gen_ai.completion", attrs=[
            {"key": "gen_ai.prompt", "value": {"stringValue": "Hi"}},
            {"key": "gen_ai.completion", "value": {"stringValue": "Hello"}},
            {"key": "gen_ai.usage.input_tokens", "value": {"intValue": 3}},
        ]))
        assert r is not None
        assert r.span_type == "agent"
        assert r.llm_input == "Hi"
        assert r.llm_output == "Hello"

    def test_error_status(self) -> None:
        span = _otlp_span(attrs=[
            {"key": "mcp.server.name", "value": {"stringValue": "s"}},
            {"key": "mcp.tool.name", "value": {"stringValue": "t"}},
        ])
        span["status"] = {"code": 2}
        r = self._call(span)
        assert r is not None
        assert r.status == "error"

    def test_double_value_attribute(self) -> None:
        r = self._call(_otlp_span(attrs=[
            {"key": "mcp.server.name", "value": {"stringValue": "s"}},
            {"key": "mcp.tool.name", "value": {"stringValue": "t"}},
            {"key": "latency", "value": {"doubleValue": 1.5}},
        ]))
        assert r is not None

    def test_bool_value_attribute(self) -> None:
        r = self._call(_otlp_span(attrs=[
            {"key": "mcp.server.name", "value": {"stringValue": "s"}},
            {"key": "mcp.tool.name", "value": {"stringValue": "t"}},
            {"key": "success", "value": {"boolValue": True}},
        ]))
        assert r is not None
