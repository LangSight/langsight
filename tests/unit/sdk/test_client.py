from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from langsight.sdk.client import LangSightClient, MCPClientProxy
from langsight.sdk.models import ToolCallSpan, ToolCallStatus


def _span(status: ToolCallStatus = ToolCallStatus.SUCCESS) -> ToolCallSpan:
    now = datetime.now(UTC)
    return ToolCallSpan(
        server_name="pg",
        tool_name="query",
        started_at=now,
        ended_at=now,
        latency_ms=42.0,
        status=status,
    )


class TestLangSightClient:
    def test_creates_with_url(self) -> None:
        client = LangSightClient(url="http://localhost:8000")
        assert client._url == "http://localhost:8000"

    def test_strips_trailing_slash(self) -> None:
        client = LangSightClient(url="http://localhost:8000/")
        assert client._url == "http://localhost:8000"

    def test_wrap_returns_proxy(self) -> None:
        client = LangSightClient(url="http://localhost:8000")
        mock_mcp = MagicMock()
        proxy = client.wrap(mock_mcp, server_name="pg")
        assert isinstance(proxy, MCPClientProxy)

    async def test_send_span_fires_task(self) -> None:
        client = LangSightClient(url="http://localhost:8000")
        span = _span()
        with patch.object(client, "_post_spans", new_callable=AsyncMock):
            # Need event loop to process tasks
            import asyncio
            task = asyncio.create_task(client.send_span(span))
            await asyncio.sleep(0)  # yield to let task fire
            await task

    async def test_post_spans_fail_open_on_network_error(self) -> None:
        client = LangSightClient(url="http://localhost:8000")
        mock_http = MagicMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(side_effect=Exception("network error"))
        client._http = mock_http
        # Should not raise — fail-open
        await client._post_spans([_span()])

    async def test_post_spans_sends_json_payload(self) -> None:
        client = LangSightClient(url="http://localhost:8000")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_http = MagicMock()
        mock_http.is_closed = False
        mock_http.post = AsyncMock(return_value=mock_response)
        client._http = mock_http
        await client._post_spans([_span()])
        mock_http.post.assert_called_once()
        call_kwargs = mock_http.post.call_args
        assert "/api/traces/spans" in call_kwargs[0][0]

    async def test_api_key_added_to_headers(self) -> None:
        client = LangSightClient(url="http://localhost:8000", api_key="secret-key")
        # _get_http creates a persistent client with headers set at init
        http = await client._get_http()
        assert http.headers.get("X-API-Key") == "secret-key"
        await client.close()


class TestMCPClientProxy:
    def test_forwards_attribute_access(self) -> None:
        mock_mcp = MagicMock()
        mock_mcp.some_property = "value"
        client = LangSightClient(url="http://localhost:8000")
        proxy = client.wrap(mock_mcp, server_name="pg")
        assert proxy.some_property == "value"

    async def test_call_tool_success_sends_span(self) -> None:
        mock_mcp = MagicMock()
        mock_mcp.call_tool = AsyncMock(return_value={"rows": []})
        langsight = LangSightClient(url="http://localhost:8000")

        with patch.object(langsight, "send_span", new_callable=AsyncMock) as mock_send:
            proxy = langsight.wrap(mock_mcp, server_name="pg")
            result = await proxy.call_tool("query", {"sql": "SELECT 1"})

        assert result == {"rows": []}
        mock_send.assert_called_once()
        span: ToolCallSpan = mock_send.call_args[0][0]
        assert span.tool_name == "query"
        assert span.server_name == "pg"
        assert span.status == ToolCallStatus.SUCCESS
        assert span.error is None

    async def test_call_tool_error_sends_error_span(self) -> None:
        mock_mcp = MagicMock()
        mock_mcp.call_tool = AsyncMock(side_effect=RuntimeError("db connection lost"))
        langsight = LangSightClient(url="http://localhost:8000")

        with patch.object(langsight, "send_span", new_callable=AsyncMock) as mock_send:
            proxy = langsight.wrap(mock_mcp, server_name="pg")
            with pytest.raises(RuntimeError):
                await proxy.call_tool("query", {"sql": "SELECT 1"})

        span: ToolCallSpan = mock_send.call_args[0][0]
        assert span.status == ToolCallStatus.ERROR
        assert "db connection lost" in span.error  # type: ignore[operator]

    async def test_call_tool_timeout_sends_timeout_span(self) -> None:
        mock_mcp = MagicMock()
        mock_mcp.call_tool = AsyncMock(side_effect=TimeoutError("timed out"))
        langsight = LangSightClient(url="http://localhost:8000")

        with patch.object(langsight, "send_span", new_callable=AsyncMock) as mock_send:
            proxy = langsight.wrap(mock_mcp, server_name="pg")
            with pytest.raises(TimeoutError):
                await proxy.call_tool("query", {})

        span: ToolCallSpan = mock_send.call_args[0][0]
        assert span.status == ToolCallStatus.TIMEOUT

    async def test_span_carries_metadata(self) -> None:
        mock_mcp = MagicMock()
        mock_mcp.call_tool = AsyncMock(return_value={})
        langsight = LangSightClient(url="http://localhost:8000")

        with patch.object(langsight, "send_span", new_callable=AsyncMock) as mock_send:
            proxy = langsight.wrap(
                mock_mcp,
                server_name="pg",
                agent_name="support-agent",
                session_id="sess-123",
                trace_id="trace-abc",
            )
            await proxy.call_tool("query", {})

        span: ToolCallSpan = mock_send.call_args[0][0]
        assert span.agent_name == "support-agent"
        assert span.session_id == "sess-123"
        assert span.trace_id == "trace-abc"

    async def test_latency_is_positive(self) -> None:
        mock_mcp = MagicMock()
        mock_mcp.call_tool = AsyncMock(return_value={})
        langsight = LangSightClient(url="http://localhost:8000")

        with patch.object(langsight, "send_span", new_callable=AsyncMock) as mock_send:
            proxy = langsight.wrap(mock_mcp, server_name="pg")
            await proxy.call_tool("query", {})

        span: ToolCallSpan = mock_send.call_args[0][0]
        assert span.latency_ms >= 0

    def test_two_line_integration_pattern(self) -> None:
        """Verify the canonical 2-line integration compiles and produces a proxy."""
        from langsight.sdk import LangSightClient

        mock_mcp = MagicMock()
        client = LangSightClient(url="http://localhost:8000")  # line 1
        traced_mcp = client.wrap(mock_mcp, server_name="my-server")  # line 2

        assert isinstance(traced_mcp, MCPClientProxy)


class TestMCPClientProxyPayloads:
    """P5.1 — proxy captures input_args and output_result on spans."""

    @pytest.mark.unit
    async def test_proxy_captures_input_args(self) -> None:
        """Span sent to LangSight has input_args matching the call arguments."""
        mock_mcp = MagicMock()
        mock_mcp.call_tool = AsyncMock(return_value={"rows": []})
        langsight = LangSightClient(url="http://localhost:8000")

        with patch.object(langsight, "send_span", new_callable=AsyncMock) as mock_send:
            proxy = langsight.wrap(mock_mcp, server_name="pg")
            await proxy.call_tool("query", {"sql": "SELECT 1"})

        span: ToolCallSpan = mock_send.call_args[0][0]
        assert span.input_args == {"sql": "SELECT 1"}

    @pytest.mark.unit
    async def test_proxy_captures_output_result(self) -> None:
        """output_result on the span is the JSON-serialised return value."""
        import json

        return_value = {"rows": [{"id": 1}]}
        mock_mcp = MagicMock()
        mock_mcp.call_tool = AsyncMock(return_value=return_value)
        langsight = LangSightClient(url="http://localhost:8000")

        with patch.object(langsight, "send_span", new_callable=AsyncMock) as mock_send:
            proxy = langsight.wrap(mock_mcp, server_name="pg")
            await proxy.call_tool("query", {"sql": "SELECT 1"})

        span: ToolCallSpan = mock_send.call_args[0][0]
        assert span.output_result == json.dumps(return_value, default=str)

    @pytest.mark.unit
    async def test_proxy_redact_omits_payloads(self) -> None:
        """Proxy with redact_payloads=True sends None for both payload fields."""
        mock_mcp = MagicMock()
        mock_mcp.call_tool = AsyncMock(return_value={"rows": []})
        langsight = LangSightClient(url="http://localhost:8000")

        with patch.object(langsight, "send_span", new_callable=AsyncMock) as mock_send:
            proxy = langsight.wrap(mock_mcp, server_name="pg", redact_payloads=True)
            await proxy.call_tool("query", {"sql": "SELECT 1"})

        span: ToolCallSpan = mock_send.call_args[0][0]
        assert span.input_args is None
        assert span.output_result is None

    @pytest.mark.unit
    async def test_proxy_redact_per_wrap_overrides_client_default(self) -> None:
        """wrap(redact_payloads=True) overrides client-level redact_payloads=False."""
        mock_mcp = MagicMock()
        mock_mcp.call_tool = AsyncMock(return_value={"rows": []})
        # Client has redact off — wrap-level override turns it on
        langsight = LangSightClient(url="http://localhost:8000", redact_payloads=False)

        with patch.object(langsight, "send_span", new_callable=AsyncMock) as mock_send:
            proxy = langsight.wrap(mock_mcp, server_name="pg", redact_payloads=True)
            await proxy.call_tool("query", {"sql": "SELECT 1"})

        span: ToolCallSpan = mock_send.call_args[0][0]
        assert span.input_args is None
        assert span.output_result is None

    @pytest.mark.unit
    async def test_proxy_output_result_none_on_error(self) -> None:
        """When the underlying call_tool raises, output_result is None in the span."""
        mock_mcp = MagicMock()
        mock_mcp.call_tool = AsyncMock(side_effect=RuntimeError("db error"))
        langsight = LangSightClient(url="http://localhost:8000")

        with patch.object(langsight, "send_span", new_callable=AsyncMock) as mock_send:
            proxy = langsight.wrap(mock_mcp, server_name="pg")
            with pytest.raises(RuntimeError):
                await proxy.call_tool("query", {"sql": "SELECT 1"})

        span: ToolCallSpan = mock_send.call_args[0][0]
        assert span.output_result is None

    @pytest.mark.unit
    async def test_proxy_output_fallback_to_str_when_not_json_serialisable(self) -> None:
        """Non-JSON-serialisable result falls back to str(result) rather than raising."""
        class _Unserializable:
            def __repr__(self) -> str:
                return "<Unserializable>"

        unserializable = _Unserializable()
        mock_mcp = MagicMock()
        mock_mcp.call_tool = AsyncMock(return_value=unserializable)
        langsight = LangSightClient(url="http://localhost:8000")

        with patch.object(langsight, "send_span", new_callable=AsyncMock) as mock_send:
            proxy = langsight.wrap(mock_mcp, server_name="pg")
            await proxy.call_tool("inspect", {})

        span: ToolCallSpan = mock_send.call_args[0][0]
        # output_result must be a string (the str() fallback), not None and not raising
        assert span.output_result is not None
        assert isinstance(span.output_result, str)
