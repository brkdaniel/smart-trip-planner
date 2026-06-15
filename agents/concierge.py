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

from agents import planner
from agents.llm_client import LLMClient, make_llm_client
from agents.tools import get_tool

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


def _format_tool_results(tool_name: str, results: list[dict]) -> str:
    """Render normalized tool results into a DATE REALE block for the prompt."""
    source = "zboruri" if tool_name == "flights" else "hoteluri"
    lines = [f"\n\n## DATE REALE — {source} (sursă: RapidAPI, în timp real)"]
    for r in results:
        parts = [str(r[k]) for k in ("title", "summary") if r.get(k)]
        price = r.get("price")
        if price:
            parts.append(f"{price} {r.get('currency', '')}".strip())
        if r.get("link"):
            parts.append(r["link"])
        lines.append("- " + " — ".join(parts))
    lines.append(
        "\nFolosește EXACT aceste opțiuni reale (prețuri, nume, ore) în răspuns "
        "și menționează că sunt date live. Nu inventa alte opțiuni."
    )
    return "\n".join(lines)


def _gather_tool_context(history, client: LLMClient | None = None) -> str:
    """A3.4: plan → run a tool → format its results, or "" if none/failed.

    Best-effort: any failure returns an empty string so the Concierge simply
    answers from general knowledge.
    """
    try:
        plan = planner.plan_tool(history, client=client)
        tool_name = plan.get("tool")
        if not tool_name:
            return ""
        tool = get_tool(tool_name)
        if tool is None:
            return ""
        result = tool.run(plan.get("params") or {})
        if not result.get("ok") or not result.get("results"):
            return ""
        return _format_tool_results(tool_name, result["results"])
    except Exception:
        logger.exception("Tool context failed (non-fatal).")
        return ""


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

    # A3.4: if the message needs real flight/hotel data, fetch it first and
    # ground the answer in it. The planner uses its own client (env provider).
    tool_context = _gather_tool_context(history)

    system = _load_system_prompt() + _render_preferences(preferences) + tool_context
    messages = _format_history(history)
    if not messages:  # defensive: empty history → use the raw prompt
        messages = [{"role": "user", "content": prompt}]

    return client.complete(messages, system)
