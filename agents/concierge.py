"""
Concierge agent (Agent 1) — the warm, user-facing travel assistant.

It owns *how* a reply is produced: it loads its system prompt, personalizes it
with the user's preferences, maps the chat history into the provider message
format and delegates the actual call to an :class:`~agents.llm_client.LLMClient`
strategy. It does **not** know which provider is behind the client.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from agents.llm_client import LLMClient, make_llm_client

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent / "prompts" / "concierge.md"

# The Concierge's provider is resolved by the factory from the LLM_PROVIDER env
# var (default "anthropic"). Set LLM_PROVIDER=gemini in .env to use Gemini.


@lru_cache(maxsize=1)
def _load_system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _render_preferences(preferences) -> str:
    """Turn a UserPreference into a short, model-friendly block.

    Accepts ``None`` gracefully (first-time users). Skips empty/default fields.
    """
    if preferences is None:
        return ""

    lines: list[str] = []
    if getattr(preferences, "dietary_preference", ""):
        lines.append(f"- Restricții alimentare: {preferences.dietary_preference}")
    if getattr(preferences, "hotel_stars", None):
        lines.append(f"- Stele hotel preferate: {preferences.hotel_stars}")
    if getattr(preferences, "travel_pace", ""):
        lines.append(f"- Ritm de călătorie: {preferences.travel_pace}")
    if getattr(preferences, "budget", None):
        lines.append(f"- Buget (orientativ): {preferences.budget}")
    if getattr(preferences, "interests", ""):
        lines.append(f"- Interese: {preferences.interests}")

    if not lines:
        return ""
    return "\n\n## Preferințele utilizatorului\n" + "\n".join(lines)


def _format_history(history) -> list[dict]:
    """Map ChatMessage objects to the provider-agnostic message format."""
    return [{"role": m.role, "content": m.content} for m in history]


def generate_reply(prompt: str, history, preferences, client: LLMClient | None = None) -> str:
    """Produce the Concierge's reply.

    :param prompt: the latest user message (already persisted by the view).
    :param history: iterable of ChatMessage in chronological order. Because the
        view saves the user turn *before* calling us, ``history`` already ends
        with ``prompt`` — so we build the message list from history and do not
        re-append it.
    :param preferences: the user's UserPreference (or ``None``).
    :param client: an LLMClient strategy; defaults to the configured provider.
        Injectable for tests.
    """
    client = client or make_llm_client()

    system = _load_system_prompt() + _render_preferences(preferences)
    messages = _format_history(history)
    if not messages:  # defensive: empty history → use the raw prompt
        messages = [{"role": "user", "content": prompt}]

    return client.complete(messages, system)
