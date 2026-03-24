"""Tests for the LLM client wrapper (wrap_llm)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from langsight.sdk.client import LangSightClient
from langsight.sdk.llm_wrapper import (
    AnthropicProxy,
    GeminiProxy,
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

    def test_detects_gemini(self, client: LangSightClient) -> None:
        fake = _make_fake("GenerativeModel", "google.generativeai")
        result = wrap_llm(fake, client, agent_name="test")
        assert isinstance(result, GeminiProxy)

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
            choices=[choice], model="gpt-4o", usage=usage,
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
            type="tool_use", name="get_weather", input={"city": "NYC"},
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
