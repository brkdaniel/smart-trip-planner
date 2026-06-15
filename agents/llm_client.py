"""
LLM client layer for the AI agents (Branch A).

Design patterns
---------------
* **Strategy** — :class:`LLMClient` is the abstract strategy. Every provider
  (Anthropic Claude, Google Gemini) and the offline :class:`EchoClient` are
  interchangeable concrete strategies exposing the exact same method::

      complete(messages: list[dict], system: str) -> str

  The agents (Concierge, and later the Data Architect) depend only on this
  abstraction, so switching providers is a one-file change.
* **Factory** — :func:`make_llm_client` builds the right strategy from the
  environment and *gracefully falls back* to :class:`EchoClient` when no API key
  or SDK is available. This keeps the app runnable offline (no key needed for a
  demo) and makes tests deterministic.

Provider SDKs (``anthropic`` / ``google-generativeai``) are imported lazily so
the project runs even before they are ``pip install``-ed.
"""

from __future__ import annotations

import importlib.util
import logging
import os
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

# Sensible, env-overridable defaults. See .env.example.
DEFAULT_PROVIDER = "anthropic"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash-lite"

# Placeholders that mean "not configured" (see .env.example).
_PLACEHOLDER_KEYS = {"", "replace-me", "your-key-here"}


# --------------------------------------------------------------------------- #
# Strategy interface
# --------------------------------------------------------------------------- #
class LLMClient(ABC):
    """Abstract strategy: a thin, provider-agnostic chat completion client."""

    @abstractmethod
    def complete(self, messages: list[dict], system: str) -> str:
        """Return the assistant's reply text.

        :param messages: chat turns as ``[{"role": "user"|"assistant",
            "content": str}, ...]`` in chronological order.
        :param system: the system prompt steering the model.
        """
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# Concrete strategies
# --------------------------------------------------------------------------- #
class AnthropicClient(LLMClient):
    """Claude via the ``anthropic`` SDK — used by the Concierge agent."""

    def __init__(self, api_key: str, model: str | None = None, max_tokens: int = 2048):
        self.api_key = api_key
        self.model = model or os.getenv("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL)
        self.max_tokens = max_tokens

    def complete(self, messages: list[dict], system: str) -> str:
        import anthropic  # lazy: only needed when actually calling the API

        client = anthropic.Anthropic(api_key=self.api_key)
        response = client.messages.create(
            model=self.model,
            system=system,
            max_tokens=self.max_tokens,
            messages=messages,
        )
        # response.content is a list of blocks; keep the text ones.
        return "".join(
            block.text for block in response.content
            if getattr(block, "type", None) == "text"
        ).strip()


class GeminiClient(LLMClient):
    """Google Gemini via ``google-generativeai`` — reserved for the Data Architect."""

    def __init__(self, api_key: str, model: str | None = None):
        self.api_key = api_key
        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)

    def complete(self, messages: list[dict], system: str) -> str:
        import google.generativeai as genai  # lazy

        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(self.model, system_instruction=system)
        # Gemini uses role "model" for the assistant and "parts" for content.
        contents = [
            {
                "role": "model" if m["role"] == "assistant" else "user",
                "parts": [m["content"]],
            }
            for m in messages
        ]
        response = model.generate_content(contents)
        return (response.text or "").strip()


class EchoClient(LLMClient):
    """Offline fallback strategy.

    Returns a deterministic, Romanian reply so the app and tests work without
    any API key or network. Picked automatically by the factory when no real
    provider is configured.
    """

    def complete(self, messages: list[dict], system: str) -> str:
        last_user = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"),
            "",
        )
        return (
            "🧭 *(răspuns demo — niciun model AI configurat)*\n\n"
            f"Am primit mesajul tău: **{last_user}**\n\n"
            "Pentru răspunsuri reale, adaugă o cheie `ANTHROPIC_API_KEY` în "
            "fișierul `.env` și repornește serverul."
        )


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #
def _clean_key(value: str | None) -> str:
    value = (value or "").strip()
    return "" if value.lower() in _PLACEHOLDER_KEYS else value


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def make_llm_client(provider: str | None = None) -> LLMClient:
    """Build an :class:`LLMClient` from config, falling back to :class:`EchoClient`.

    Resolution order for ``provider``: explicit argument → ``LLM_PROVIDER`` env
    var → :data:`DEFAULT_PROVIDER`. If the chosen provider has no API key or its
    SDK isn't installed, returns :class:`EchoClient` instead of crashing.
    """
    provider = (provider or os.getenv("LLM_PROVIDER") or DEFAULT_PROVIDER).strip().lower()

    if provider == "anthropic":
        key = _clean_key(os.getenv("ANTHROPIC_API_KEY"))
        if key and _module_available("anthropic"):
            return AnthropicClient(api_key=key)
        logger.warning(
            "Anthropic indisponibil (cheie API sau SDK lipsă) — folosesc EchoClient."
        )
    elif provider == "gemini":
        key = _clean_key(os.getenv("GOOGLE_API_KEY"))
        if key and _module_available("google.generativeai"):
            return GeminiClient(api_key=key)
        logger.warning(
            "Gemini indisponibil (cheie API sau SDK lipsă) — folosesc EchoClient."
        )
    else:
        logger.warning("Provider LLM necunoscut '%s' — folosesc EchoClient.", provider)

    return EchoClient()
