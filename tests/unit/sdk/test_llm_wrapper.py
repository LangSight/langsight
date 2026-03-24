"""Tests for the LLM client wrapper (wrap_llm)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from langsight.sdk.client import LangSightClient
from langsight.sdk.llm_wrapper import (
    AnthropicProxy,
    GeminiProxy,
    GenaiClientProxy,
    OpenAIProxy,
    wrap_llm,
)


@pytest.fixture
def client() -> LangSightClient:
    return LangSightClient(url="http://localhost:8000")


# =============================================================================
# Auto-detection
# =============================================================================


def _make_fake(name: str, module: str) -> object:
    """Create a fake object whose type has the given name and module."""
    cls = type(name, (), {"__module__": module})
    return cls()


class TestAutoDetection:
    def test_detects_openai(self, client: LangSightClient) -> None:
        fake = _make_fake("OpenAI", "openai")
        result = wrap_llm(fake, client, agent_name="test")
        assert isinstance(result, OpenAIProxy)

    def test_detects_anthropic(self, client: LangSightClient) -> None:
        fake = _make_fake("Anthropic", "anthropic")
        result = wrap_llm(fake, client, agent_name="test")
        assert isinstance(result, AnthropicProxy)

    def test_detects_gemini_legacy(self, client: LangSightClient) -> None:
        fake = _make_fake("GenerativeModel", "google.generativeai.generative_models")
        result = wrap_llm(fake, client, agent_name="test")
        assert isinstance(result, GeminiProxy)

    def test_detects_genai_client(self, client: LangSightClient) -> None:
        """New google.genai.Client should be detected as GenaiClientProxy."""
        fake = _make_fake("Client", "google.genai.client")
        result = wrap_llm(fake, client, agent_name="test")
        assert isinstance(result, GenaiClientProxy)

    def test_genai_client_takes_priority(self, client: LangSightClient) -> None:
        """google.genai.Client must NOT fall through to the legacy GeminiProxy."""
        fake = _make_fake("Client", "google.genai.client")
        result = wrap_llm(fake, client, agent_name="test")
        assert not isinstance(result, GeminiProxy)
        assert isinstance(result, GenaiClientProxy)

    def test_unknown_returns_original(self, client: LangSightClient) -> None:
        fake = _make_fake("CustomLLM", "my_custom_module")
        result = wrap_llm(fake, client, agent_name="test")
        assert result is fake


# =============================================================================
# OpenAI proxy
# =============================================================================


class TestOpenAIProxy:
    def test_forwards_attributes(self, client: LangSightClient) -> None:
        fake = SimpleNamespace(model="gpt-4o", api_key="sk-test")
        proxy = OpenAIProxy(fake, client, agent_name="test")
        assert proxy.model == "gpt-4o"
        assert proxy.api_key == "sk-test"

    def test_chat_completions_create_intercepts(self, client: LangSightClient) -> None:
        # Build a mock OpenAI response
        tool_call = SimpleNamespace(
            function=SimpleNamespace(name="search", arguments='{"q": "test"}'),
        )
        message = SimpleNamespace(tool_calls=[tool_call], content=None)
        choice = SimpleNamespace(message=message)
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=50)
        response = SimpleNamespace(
            choices=[choice],
            model="gpt-4o",
            usage=usage,
        )

        fake_client = SimpleNamespace()
        fake_client.chat = SimpleNamespace()
        fake_client.chat.completions = SimpleNamespace()
        fake_client.chat.completions.create = lambda **kw: response

        proxy = OpenAIProxy(fake_client, client, agent_name="my-agent")

        with patch.object(proxy, "_emit_spans") as mock_emit:
            result = proxy.chat.completions.create(model="gpt-4o", messages=[])

        assert result is response
        assert mock_emit.called
        spans = mock_emit.call_args[0][0]
        assert len(spans) == 2  # 1 LLM span + 1 tool span
        assert spans[0].tool_name == "generate/gpt-4o"
        assert spans[0].span_type == "agent"
        assert spans[0].input_tokens == 100
        assert spans[0].output_tokens == 50
        assert spans[1].tool_name == "search"
        assert spans[1].span_type == "tool_call"
        assert spans[1].parent_span_id == spans[0].span_id

    def test_no_tool_calls_still_emits_llm_span(self, client: LangSightClient) -> None:
        message = SimpleNamespace(tool_calls=None, content="Hello!")
        choice = SimpleNamespace(message=message)
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5)
        response = SimpleNamespace(choices=[choice], model="gpt-4o", usage=usage)

        fake_client = SimpleNamespace()
        fake_client.chat = SimpleNamespace()
        fake_client.chat.completions = SimpleNamespace()
        fake_client.chat.completions.create = lambda **kw: response

        proxy = OpenAIProxy(fake_client, client, agent_name="agent")

        with patch.object(proxy, "_emit_spans") as mock_emit:
            proxy.chat.completions.create(model="gpt-4o", messages=[])

        spans = mock_emit.call_args[0][0]
        assert len(spans) == 1  # Just the LLM span
        assert spans[0].tool_name == "generate/gpt-4o"


# =============================================================================
# Anthropic proxy
# =============================================================================


class TestAnthropicProxy:
    def test_messages_create_intercepts(self, client: LangSightClient) -> None:
        tool_block = SimpleNamespace(
            type="tool_use",
            name="get_weather",
            input={"city": "NYC"},
        )
        text_block = SimpleNamespace(type="text", text="Let me check...")
        usage = SimpleNamespace(input_tokens=200, output_tokens=80)
        response = SimpleNamespace(
            content=[text_block, tool_block],
            model="claude-sonnet-4-6",
            usage=usage,
        )

        fake_client = SimpleNamespace()
        fake_client.messages = SimpleNamespace()
        fake_client.messages.create = lambda **kw: response

        proxy = AnthropicProxy(fake_client, client, agent_name="claude-agent")

        with patch.object(proxy, "_emit_spans") as mock_emit:
            result = proxy.messages.create(model="claude-sonnet-4-6", messages=[])

        assert result is response
        spans = mock_emit.call_args[0][0]
        assert len(spans) == 2
        assert spans[0].tool_name == "generate/claude-sonnet-4-6"
        assert spans[0].input_tokens == 200
        assert spans[1].tool_name == "get_weather"
        assert spans[1].parent_span_id == spans[0].span_id


# =============================================================================
# Gemini proxy
# =============================================================================


class TestGeminiProxy:
    def test_generate_content_intercepts(self, client: LangSightClient) -> None:
        fn_call = SimpleNamespace(name="search_db", args={"query": "SELECT 1"})
        part = SimpleNamespace(function_call=fn_call)
        content = SimpleNamespace(parts=[part])
        candidate = SimpleNamespace(content=content)
        usage = SimpleNamespace(prompt_token_count=150, candidates_token_count=60)
        response = SimpleNamespace(candidates=[candidate], usage_metadata=usage)

        fake_model = SimpleNamespace(model_name="gemini-2.5-flash")
        fake_model.generate_content = lambda *a, **kw: response

        proxy = GeminiProxy(fake_model, client, agent_name="analyst")

        with patch.object(proxy, "_emit_spans") as mock_emit:
            result = proxy.generate_content("test prompt")

        assert result is response
        spans = mock_emit.call_args[0][0]
        assert len(spans) == 2
        assert spans[0].tool_name == "generate/gemini-2.5-flash"
        assert spans[0].input_tokens == 150
        assert spans[1].tool_name == "search_db"
        assert spans[1].parent_span_id == spans[0].span_id

    def test_no_function_calls_still_emits_llm_span(self, client: LangSightClient) -> None:
        text_part = SimpleNamespace(function_call=None, text="Hello!")
        content = SimpleNamespace(parts=[text_part])
        candidate = SimpleNamespace(content=content)
        usage = SimpleNamespace(prompt_token_count=10, candidates_token_count=5)
        response = SimpleNamespace(candidates=[candidate], usage_metadata=usage)

        fake_model = SimpleNamespace(model_name="gemini-2.5-flash")
        fake_model.generate_content = lambda *a, **kw: response

        proxy = GeminiProxy(fake_model, client, agent_name="agent")

        with patch.object(proxy, "_emit_spans") as mock_emit:
            proxy.generate_content("test")

        spans = mock_emit.call_args[0][0]
        assert len(spans) == 1


# =============================================================================
# LangSightClient.wrap_llm()
# =============================================================================


class TestClientWrapLLM:
    def test_wrap_llm_method_exists(self, client: LangSightClient) -> None:
        assert hasattr(client, "wrap_llm")
        assert callable(client.wrap_llm)

    def test_wrap_llm_returns_proxy_for_known_sdk(self, client: LangSightClient) -> None:
        fake = _make_fake("OpenAI", "openai")
        result = client.wrap_llm(fake, agent_name="test")
        assert isinstance(result, OpenAIProxy)

    def test_wrap_llm_returns_original_for_unknown(self, client: LangSightClient) -> None:
        fake = _make_fake("UnknownLLM", "some.module")
        result = client.wrap_llm(fake, agent_name="test")
        assert result is fake


# =============================================================================
# GenAI Client proxy (new google.genai SDK)
# =============================================================================


def _make_genai_response(
    function_calls: list[SimpleNamespace] | None = None,
    prompt_tokens: int = 100,
    output_tokens: int = 50,
) -> SimpleNamespace:
    """Build a mock google.genai response with optional function calls."""
    parts = []
    if function_calls:
        for fc in function_calls:
            parts.append(SimpleNamespace(function_call=fc))
    else:
        parts.append(SimpleNamespace(function_call=None, text="Hello!"))

    content = SimpleNamespace(parts=parts)
    candidate = SimpleNamespace(content=content)
    usage = SimpleNamespace(
        prompt_token_count=prompt_tokens,
        candidates_token_count=output_tokens,
    )
    return SimpleNamespace(candidates=[candidate], usage_metadata=usage)


class TestGenaiClientProxy:
    def test_sync_models_generate_content(self, client: LangSightClient) -> None:
        """client.models.generate_content() should be intercepted."""
        fn_call = SimpleNamespace(name="list_products", args={"category": "Electronics"})
        response = _make_genai_response(function_calls=[fn_call])

        fake_genai = SimpleNamespace()
        fake_genai.models = SimpleNamespace()
        fake_genai.models.generate_content = lambda **kw: response

        proxy = GenaiClientProxy(fake_genai, client, agent_name="orchestrator")

        with patch.object(proxy, "_emit_spans") as mock_emit:
            result = proxy.models.generate_content(
                model="gemini-2.5-flash",
                contents=[],
                config=None,
            )

        assert result is response
        assert mock_emit.called
        spans = mock_emit.call_args[0][0]
        assert len(spans) == 2  # 1 LLM span + 1 tool span
        assert spans[0].tool_name == "generate/gemini-2.5-flash"
        assert spans[0].span_type == "agent"
        assert spans[0].model_id == "gemini-2.5-flash"
        assert spans[0].input_tokens == 100
        assert spans[0].output_tokens == 50
        assert spans[1].tool_name == "list_products"
        assert spans[1].span_type == "tool_call"
        assert spans[1].parent_span_id == spans[0].span_id

    @pytest.mark.asyncio
    async def test_async_aio_models_generate_content(self, client: LangSightClient) -> None:
        """client.aio.models.generate_content() should be intercepted."""
        fn_call = SimpleNamespace(name="get_stock_level", args={"product_id": 3})
        response = _make_genai_response(function_calls=[fn_call])

        async def fake_generate(**kw: object) -> SimpleNamespace:
            return response

        fake_genai = SimpleNamespace()
        fake_genai.aio = SimpleNamespace()
        fake_genai.aio.models = SimpleNamespace()
        fake_genai.aio.models.generate_content = fake_generate

        proxy = GenaiClientProxy(fake_genai, client, agent_name="analyst")

        with patch.object(proxy, "_emit_spans") as mock_emit:
            result = await proxy.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=[],
                config=None,
            )

        assert result is response
        assert mock_emit.called
        spans = mock_emit.call_args[0][0]
        assert len(spans) == 2
        assert spans[0].tool_name == "generate/gemini-2.5-flash"
        assert spans[1].tool_name == "get_stock_level"

    def test_model_name_from_kwarg(self, client: LangSightClient) -> None:
        """Model name should come from the model= kwarg, not from client attrs."""
        response = _make_genai_response()
        fake_genai = SimpleNamespace()
        fake_genai.models = SimpleNamespace()
        fake_genai.models.generate_content = lambda **kw: response

        proxy = GenaiClientProxy(fake_genai, client, agent_name="test")

        with patch.object(proxy, "_emit_spans") as mock_emit:
            proxy.models.generate_content(model="gemini-2.5-pro", contents=[])

        span = mock_emit.call_args[0][0][0]
        assert span.model_id == "gemini-2.5-pro"
        assert span.tool_name == "generate/gemini-2.5-pro"

    def test_no_function_calls_emits_llm_span(self, client: LangSightClient) -> None:
        """Response without function calls still produces an LLM generation span."""
        response = _make_genai_response()  # no function_calls
        fake_genai = SimpleNamespace()
        fake_genai.models = SimpleNamespace()
        fake_genai.models.generate_content = lambda **kw: response

        proxy = GenaiClientProxy(fake_genai, client, agent_name="test")

        with patch.object(proxy, "_emit_spans") as mock_emit:
            proxy.models.generate_content(model="gemini-2.5-flash", contents=[])

        spans = mock_emit.call_args[0][0]
        assert len(spans) == 1
        assert spans[0].span_type == "agent"

    def test_forwards_other_attributes(self, client: LangSightClient) -> None:
        """Attributes not intercepted should forward to the real client."""
        fake_genai = SimpleNamespace(api_key="test-key", some_attr=42)
        proxy = GenaiClientProxy(fake_genai, client, agent_name="test")
        assert proxy.api_key == "test-key"
        assert proxy.some_attr == 42

    def test_response_returned_unchanged(self, client: LangSightClient) -> None:
        """The proxy must return the exact same response object (identity)."""
        response = _make_genai_response()
        fake_genai = SimpleNamespace()
        fake_genai.models = SimpleNamespace()
        fake_genai.models.generate_content = lambda **kw: response

        proxy = GenaiClientProxy(fake_genai, client, agent_name="test")
        result = proxy.models.generate_content(model="gemini-2.5-flash", contents=[])
        assert result is response


# =============================================================================
# _emit_spans uses buffer_span (not send_spans)
# =============================================================================


class TestEmitSpansUsesBufferSpan:
    def test_emit_spans_calls_buffer_span(self, client: LangSightClient) -> None:
        """_emit_spans must call buffer_span() synchronously, not send_spans()."""
        from langsight.sdk.models import ToolCallSpan, ToolCallStatus

        span = ToolCallSpan.record(
            server_name="test",
            tool_name="test_tool",
            started_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            status=ToolCallStatus.SUCCESS,
        )

        client.buffer_span = MagicMock()  # type: ignore[assignment]
        proxy = OpenAIProxy(SimpleNamespace(), client, agent_name="test")
        proxy._emit_spans([span])

        client.buffer_span.assert_called_once_with(span)
