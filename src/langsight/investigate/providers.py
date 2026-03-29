"""
LLM provider abstractions for langsight investigate.

Each provider implements the LLMProvider Protocol:
    async def analyse(evidence: str, system: str) -> str

Supported providers:
    anthropic  — Claude (claude-sonnet-4-6)
    openai     — OpenAI GPT (gpt-4o, gpt-4o-mini, o1-mini, ...)
    gemini     — Google Gemini via OpenAI-compatible endpoint
    ollama     — Local models via Ollama (llama3.2, mistral, ...)

Select via .langsight.yaml:
    investigate:
      provider: gemini
      model: gemini-2.0-flash
      api_key: ${GEMINI_API_KEY}   # or set env var directly
"""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

import structlog

from langsight.exceptions import ConfigError

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Default models per provider
# ---------------------------------------------------------------------------
_DEFAULTS = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o",
    "gemini": "gemini-2.0-flash",
    "ollama": "llama3.2",
}

# Gemini's OpenAI-compatible base URL
_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

# Ollama local base URL
_OLLAMA_BASE_URL = "http://localhost:11434/v1"


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMProvider(Protocol):
    """Interface every LLM provider must implement."""

    async def analyse(self, evidence: str, system: str) -> str:
        """Send evidence to the LLM and return the RCA report as a string."""
        ...

    @property
    def display_name(self) -> str:
        """Human-readable name shown in the terminal (e.g. 'Claude claude-sonnet-4-6')."""
        ...


# ---------------------------------------------------------------------------
# Anthropic (Claude)
# ---------------------------------------------------------------------------


class AnthropicProvider:
    """Claude via the Anthropic SDK.

    Requires: ANTHROPIC_API_KEY environment variable.
    Get a key: https://console.anthropic.com
    """

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self._model = model or _DEFAULTS["anthropic"]
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY") or ""
        if not self._api_key:
            raise ConfigError(
                "ANTHROPIC_API_KEY not set. "
                "Get a key at https://console.anthropic.com and set:\n"
                "  export ANTHROPIC_API_KEY=sk-ant-..."
            )

    @property
    def display_name(self) -> str:
        return f"Claude  {self._model}"

    async def analyse(self, evidence: str, system: str) -> str:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=self._api_key)
        response = await client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": evidence}],
        )
        return next((b.text for b in response.content if b.type == "text"), "")


# ---------------------------------------------------------------------------
# OpenAI (GPT-4o, o1-mini, etc.)
# ---------------------------------------------------------------------------


class OpenAIProvider:
    """OpenAI GPT models via the OpenAI SDK.

    Requires: OPENAI_API_KEY environment variable.
    Get a key: https://platform.openai.com/api-keys
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._model = model or _DEFAULTS["openai"]
        self._api_key = api_key or os.getenv("OPENAI_API_KEY") or ""
        self._base_url = base_url
        if not self._api_key:
            raise ConfigError(
                "OPENAI_API_KEY not set. "
                "Get a key at https://platform.openai.com/api-keys and set:\n"
                "  export OPENAI_API_KEY=sk-..."
            )

    @property
    def display_name(self) -> str:
        return f"OpenAI  {self._model}"

    async def analyse(self, evidence: str, system: str) -> str:
        from openai import AsyncOpenAI

        if self._base_url:
            client = AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
        else:
            client = AsyncOpenAI(api_key=self._api_key)
        response = await client.chat.completions.create(
            model=self._model,
            max_tokens=2048,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": evidence},
            ],
        )
        return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Gemini (via OpenAI-compatible endpoint)
# ---------------------------------------------------------------------------


class GeminiProvider:
    """Google Gemini via its OpenAI-compatible API endpoint.

    Uses the OpenAI SDK — no extra dependency needed.

    Requires: GEMINI_API_KEY environment variable.
    Get a free key (1500 req/day): https://aistudio.google.com/app/apikey

    Recommended models:
        gemini-2.0-flash    — fast, cheap, great for RCA (default)
        gemini-2.5-pro      — best quality, 1M context
        gemini-1.5-flash    — budget option
    """

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self._model = model or _DEFAULTS["gemini"]
        self._api_key = api_key or os.getenv("GEMINI_API_KEY") or ""
        if not self._api_key:
            raise ConfigError(
                "GEMINI_API_KEY not set. "
                "Get a free key at https://aistudio.google.com/app/apikey and set:\n"
                "  export GEMINI_API_KEY=AIza..."
            )

    @property
    def display_name(self) -> str:
        return f"Gemini  {self._model}"

    async def analyse(self, evidence: str, system: str) -> str:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=_GEMINI_BASE_URL,
        )
        response = await client.chat.completions.create(
            model=self._model,
            max_tokens=2048,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": evidence},
            ],
        )
        return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Ollama (local, free)
# ---------------------------------------------------------------------------


class OllamaProvider:
    """Local LLMs via Ollama — completely free, runs on your machine.

    Requires: Ollama running locally (https://ollama.com/download)
    No API key needed.

    Setup:
        1. Install: https://ollama.com/download
        2. Pull a model: ollama pull llama3.2
        3. Ollama runs automatically on http://localhost:11434

    Recommended models:
        llama3.2        — 3B, fast, good reasoning (default)
        llama3.1:8b     — 8B, better quality, needs ~8GB RAM
        mistral         — 7B, strong at structured analysis
        qwen2.5:14b     — 14B, excellent quality if you have GPU

    Custom base_url for remote Ollama instances:
        base_url: http://my-server:11434/v1
    """

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._model = model or _DEFAULTS["ollama"]
        self._base_url = base_url or _OLLAMA_BASE_URL

    @property
    def display_name(self) -> str:
        return f"Ollama  {self._model}"

    async def analyse(self, evidence: str, system: str) -> str:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key="ollama",  # Ollama accepts any non-empty string
            base_url=self._base_url,
        )
        try:
            response = await client.chat.completions.create(
                model=self._model,
                max_tokens=2048,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": evidence},
                ],
            )
            return response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001
            raise ConfigError(
                f"Ollama request failed: {exc}\n"
                f"Is Ollama running? Try: ollama serve\n"
                f"Is the model pulled? Try: ollama pull {self._model}"
            ) from exc


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_provider(
    provider: str,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> LLMProvider:
    """Create an LLMProvider from a provider name string.

    Args:
        provider: "anthropic" | "openai" | "gemini" | "ollama"
        model: Override the default model for this provider.
        api_key: Override the default env-var API key.
        base_url: Override the default base URL (useful for Ollama remotes).

    Raises:
        ConfigError: if provider is unknown or required credentials are missing.
    """
    name = provider.lower().strip()

    if name == "anthropic":
        return AnthropicProvider(model=model, api_key=api_key)
    if name == "openai":
        return OpenAIProvider(model=model, api_key=api_key, base_url=base_url)
    if name == "gemini":
        return GeminiProvider(model=model, api_key=api_key)
    if name == "ollama":
        return OllamaProvider(model=model, base_url=base_url)

    raise ConfigError(
        f"Unknown investigate provider '{provider}'. "
        "Valid values: anthropic, openai, gemini, ollama.\n"
        "See docs/06-provider-setup.md for setup instructions."
    )
