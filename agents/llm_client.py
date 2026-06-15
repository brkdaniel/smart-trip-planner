"""
LLM client layer for the AI agents (Branch A).

Design patterns
---------------
* **Strategy** — :class:`LLMClient` is the abstract strategy. The provider
  (Google Gemini) and the offline :class:`EchoClient` are interchangeable
  concrete strategies exposing the exact same method::

      complete(messages: list[dict], system: str) -> str

  The agents (Concierge, Data Architect) depend only on this abstraction.
* **Factory** — :func:`make_llm_client` builds the strategy from the environment
  and *gracefully falls back* to :class:`EchoClient` when no API key or SDK is
  available. This keeps the app runnable offline (no key needed for a demo) and
  makes tests deterministic.

The Gemini SDK (``google-generativeai``) is imported lazily so the project runs
even before it is ``pip install``-ed.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import time
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)
# A3.3: dedicated logger for per-call LLM telemetry (writes to a log file; see
# LOGGING in settings.py).
llm_logger = logging.getLogger("agents.llm")

# Sensible, env-overridable defaults. See .env.example.
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash-lite"

# Placeholders that mean "not configured" (see .env.example).
_PLACEHOLDER_KEYS = {"", "replace-me", "your-key-here"}


# --------------------------------------------------------------------------- #
# A3.3 — per-call telemetry
# --------------------------------------------------------------------------- #
def _log_llm_call(provider, model, started, *, ok, tokens=None, error=None):
    """Log one LLM call: provider, model, latency, token usage, success/fail."""
    latency_ms = int((time.perf_counter() - started) * 1000)
    if ok:
        llm_logger.info(
            "provider=%s model=%s latency_ms=%d ok=1 tokens=%s",
            provider, model, latency_ms, tokens if tokens is not None else "-",
        )
    else:
        llm_logger.warning(
            "provider=%s model=%s latency_ms=%d ok=0 error=%s",
            provider, model, latency_ms, error,
        )


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
class GeminiClient(LLMClient):
    """Google Gemini via ``google-generativeai`` — the project's only provider."""

    def __init__(self, api_key: str, model: str | None = None):
        self.api_key = api_key
        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)

    def complete(self, messages: list[dict], system: str) -> str:
        import google.generativeai as genai  # lazy

        started = time.perf_counter()
        try:
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
            text = (response.text or "").strip()
            usage = getattr(response, "usage_metadata", None)
            tokens = getattr(usage, "total_token_count", None) if usage else None
            _log_llm_call("gemini", self.model, started, ok=True, tokens=tokens)
            return text
        except Exception as exc:
            _log_llm_call("gemini", self.model, started, ok=False, error=exc)
            raise


class EchoClient(LLMClient):
    """Offline fallback strategy.

    Returns a deterministic, Romanian reply so the app and tests work without
    any API key or network. Picked automatically by the factory when no real
    provider is configured.
    """

    def complete(self, messages: list[dict], system: str) -> str:
        started = time.perf_counter()
        last_user = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"),
            "",
        )
        _log_llm_call("echo", "echo", started, ok=True, tokens=0)
        return (
            "🧭 *(răspuns demo — niciun model AI configurat)*\n\n"
            f"Am primit mesajul tău: **{last_user}**\n\n"
            "Pentru răspunsuri reale, adaugă o cheie `GOOGLE_API_KEY` în "
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
    """Build an :class:`LLMClient`, falling back to :class:`EchoClient`.

    Gemini is the project's only provider. The ``provider`` argument and the
    ``LLM_PROVIDER`` env var are accepted for backward compatibility but ignored
    — everything routes to Gemini. If there's no ``GOOGLE_API_KEY`` or the SDK
    isn't installed, returns :class:`EchoClient` instead of crashing.
    """
    key = _clean_key(os.getenv("GOOGLE_API_KEY"))
    if key and _module_available("google.generativeai"):
        return GeminiClient(api_key=key)

    logger.warning(
        "Gemini indisponibil (cheie API sau SDK lipsă) — folosesc EchoClient."
    )
    return EchoClient()
