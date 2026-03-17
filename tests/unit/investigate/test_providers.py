from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from langsight.exceptions import ConfigError
from langsight.investigate.providers import (
    AnthropicProvider,
    GeminiProvider,
    OllamaProvider,
    OpenAIProvider,
    create_provider,
)


class TestCreateProvider:
    def test_creates_anthropic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        p = create_provider("anthropic")
        assert isinstance(p, AnthropicProvider)

    def test_creates_openai(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        p = create_provider("openai")
        assert isinstance(p, OpenAIProvider)

    def test_creates_gemini(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
        p = create_provider("gemini")
        assert isinstance(p, GeminiProvider)

    def test_creates_ollama_no_key_needed(self) -> None:
        p = create_provider("ollama")
        assert isinstance(p, OllamaProvider)

    def test_case_insensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
        p = create_provider("Gemini")
        assert isinstance(p, GeminiProvider)

    def test_unknown_provider_raises_config_error(self) -> None:
        with pytest.raises(ConfigError, match="Unknown investigate provider"):
            create_provider("cohere")

    def test_model_override_applied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
        p = create_provider("gemini", model="gemini-2.5-pro")
        assert isinstance(p, GeminiProvider)
        assert p._model == "gemini-2.5-pro"


class TestAnthropicProvider:
    def test_raises_config_error_without_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
            AnthropicProvider()

    def test_display_name_includes_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        p = AnthropicProvider(model="claude-sonnet-4-6")
        assert "claude-sonnet-4-6" in p.display_name
        assert "Claude" in p.display_name

    def test_default_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        p = AnthropicProvider()
        assert p._model == "claude-sonnet-4-6"

    async def test_analyse_calls_anthropic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        p = AnthropicProvider()

        mock_block = MagicMock()
        mock_block.type = "text"
        mock_block.text = "Root cause: timeout"
        mock_response = MagicMock()
        mock_response.content = [mock_block]

        with patch("anthropic.AsyncAnthropic") as MockClient:
            MockClient.return_value.messages.create = AsyncMock(return_value=mock_response)
            result = await p.analyse("evidence text", "system prompt")

        assert result == "Root cause: timeout"


class TestOpenAIProvider:
    def test_raises_config_error_without_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
            OpenAIProvider()

    def test_display_name_includes_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        p = OpenAIProvider(model="gpt-4o")
        assert "gpt-4o" in p.display_name
        assert "OpenAI" in p.display_name

    def test_default_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        p = OpenAIProvider()
        assert p._model == "gpt-4o"

    async def test_analyse_calls_openai(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        p = OpenAIProvider()

        mock_choice = MagicMock()
        mock_choice.message.content = "Root cause: auth error"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        with patch("openai.AsyncOpenAI") as MockClient:
            MockClient.return_value.chat.completions.create = AsyncMock(return_value=mock_response)
            result = await p.analyse("evidence", "system")

        assert result == "Root cause: auth error"


class TestGeminiProvider:
    def test_raises_config_error_without_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with pytest.raises(ConfigError, match="GEMINI_API_KEY"):
            GeminiProvider()

    def test_display_name_includes_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
        p = GeminiProvider(model="gemini-2.0-flash")
        assert "gemini-2.0-flash" in p.display_name
        assert "Gemini" in p.display_name

    def test_default_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
        p = GeminiProvider()
        assert p._model == "gemini-2.0-flash"

    async def test_analyse_uses_gemini_base_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
        p = GeminiProvider()

        mock_choice = MagicMock()
        mock_choice.message.content = "Schema drift detected"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        with patch("openai.AsyncOpenAI") as MockClient:
            MockClient.return_value.chat.completions.create = AsyncMock(return_value=mock_response)
            result = await p.analyse("evidence", "system")

        # Verify it used the Gemini base URL
        call_kwargs = MockClient.call_args[1]
        assert "generativelanguage.googleapis.com" in call_kwargs.get("base_url", "")
        assert result == "Schema drift detected"


class TestOllamaProvider:
    def test_no_api_key_required(self) -> None:
        p = OllamaProvider()
        assert p is not None

    def test_display_name_includes_model(self) -> None:
        p = OllamaProvider(model="llama3.2")
        assert "llama3.2" in p.display_name
        assert "Ollama" in p.display_name

    def test_default_model(self) -> None:
        p = OllamaProvider()
        assert p._model == "llama3.2"

    def test_custom_base_url(self) -> None:
        p = OllamaProvider(base_url="http://my-server:11434/v1")
        assert p._base_url == "http://my-server:11434/v1"

    async def test_analyse_calls_ollama(self) -> None:
        p = OllamaProvider()

        mock_choice = MagicMock()
        mock_choice.message.content = "High latency on postgres-mcp"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        with patch("openai.AsyncOpenAI") as MockClient:
            MockClient.return_value.chat.completions.create = AsyncMock(return_value=mock_response)
            result = await p.analyse("evidence", "system")

        assert result == "High latency on postgres-mcp"

    async def test_analyse_raises_config_error_when_ollama_down(self) -> None:
        p = OllamaProvider()

        with patch("openai.AsyncOpenAI") as MockClient:
            MockClient.return_value.chat.completions.create = AsyncMock(
                side_effect=Exception("Connection refused")
            )
            with pytest.raises(ConfigError, match="Ollama request failed"):
                await p.analyse("evidence", "system")
