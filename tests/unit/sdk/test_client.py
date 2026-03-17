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
        with patch.object(client, "_post_spans", new_callable=AsyncMock) as mock_post:
            # Need event loop to process tasks
            import asyncio
            task = asyncio.create_task(client.send_span(span))
            await asyncio.sleep(0)  # yield to let task fire
            await task

    async def test_post_spans_fail_open_on_network_error(self) -> None:
        client = LangSightClient(url="http://localhost:8000")
        with patch("langsight.sdk.client.httpx.AsyncClient") as MockHttp:
            MockHttp.return_value.__aenter__ = AsyncMock(return_value=MockHttp.return_value)
            MockHttp.return_value.__aexit__ = AsyncMock(return_value=None)
            MockHttp.return_value.post = AsyncMock(side_effect=Exception("network error"))
            # Should not raise — fail-open
            await client._post_spans([_span()])

    async def test_post_spans_sends_json_payload(self) -> None:
        client = LangSightClient(url="http://localhost:8000")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        with patch("langsight.sdk.client.httpx.AsyncClient") as MockHttp:
            MockHttp.return_value.__aenter__ = AsyncMock(return_value=MockHttp.return_value)
            MockHttp.return_value.__aexit__ = AsyncMock(return_value=None)
            MockHttp.return_value.post = AsyncMock(return_value=mock_response)
            await client._post_spans([_span()])
        MockHttp.return_value.post.assert_called_once()
        call_kwargs = MockHttp.return_value.post.call_args
        assert "/api/traces/spans" in call_kwargs[0][0]

    async def test_api_key_added_to_headers(self) -> None:
        client = LangSightClient(url="http://localhost:8000", api_key="secret-key")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        with patch("langsight.sdk.client.httpx.AsyncClient") as MockHttp:
            MockHttp.return_value.__aenter__ = AsyncMock(return_value=MockHttp.return_value)
            MockHttp.return_value.__aexit__ = AsyncMock(return_value=None)
            MockHttp.return_value.post = AsyncMock(return_value=mock_response)
            await client._post_spans([_span()])
        headers = MockHttp.return_value.post.call_args[1]["headers"]
        assert headers.get("Authorization") == "Bearer secret-key"


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
