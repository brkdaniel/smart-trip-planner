"""
Tool planner (A3.4) — first pass of the two-pass tool flow.

Decides whether the user's latest message needs real flight/hotel data and
extracts the parameters, as strict JSON. A cheap keyword gate avoids spending an
LLM call on messages that clearly aren't about booking.
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

from django.utils import timezone

from agents.llm_client import LLMClient, make_llm_client

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent / "prompts" / "tool_planner.md"

# Cheap pre-filter: only call the planner LLM if the message smells like a
# booking or a directions/transport request.
_KEYWORDS = (
    "zbor", "zboruri", "bilet", "avion", "flight", "fly",
    "hotel", "hoteluri", "cazare", "booking", "hostel", "pensiune",
    # directions / transport
    "cum ajung", "cum merg", "cum pot ajunge", "direcți", "directii",
    "rută", "ruta", "traseu", "transport", "metrou", "autobuz", "tren",
    "navet", "aeroport",
)

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


@lru_cache(maxsize=1)
def _load_system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def needs_tool(text: str) -> bool:
    """True if the text mentions flights or hotels (cheap keyword gate)."""
    low = (text or "").lower()
    return any(kw in low for kw in _KEYWORDS)


def _parse_json(raw: str) -> dict:
    cleaned = _FENCE_RE.sub("", (raw or "").strip()).strip()
    if not cleaned:
        return {}
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _transcript(history) -> str:
    return "\n".join(f"{m.role}: {m.content}" for m in history)


def plan_tool(history, client: LLMClient | None = None) -> dict:
    """Return ``{"tool": "flights"|"hotels"|None, "params": {...}}``.

    Never raises: any problem yields ``{"tool": None, "params": {}}``.
    """
    none_result = {"tool": None, "params": {}}
    hist = list(history)
    last_user = next((m.content for m in reversed(hist) if m.role == "user"), "")
    # Gate: run the planner if the latest user message OR the assistant's last
    # turn mentions flights/hotels. The second case lets a short follow-up
    # answer like "din Stockholm" re-trigger a search after the Concierge asked
    # for a missing detail (departure/date) — that answer has no keyword itself.
    last_assistant = next((m.content for m in reversed(hist) if m.role == "assistant"), "")
    if not (needs_tool(last_user) or needs_tool(last_assistant)):
        return none_result

    try:
        client = client or make_llm_client()
        # Give the model today's date so it resolves partial dates ("19 iunie")
        # to the right YEAR instead of guessing a past one.
        today = timezone.localdate().isoformat()
        user_content = (
            f"Data de azi este {today}.\n\n"
            + _transcript(history)
            + "\n\nRăspunde cu JSON."
        )
        raw = client.complete(
            [{"role": "user", "content": user_content}],
            _load_system_prompt(),
        )
        data = _parse_json(raw)
        tool = data.get("tool")
        if tool not in ("flights", "hotels", "directions"):
            return none_result
        return {"tool": tool, "params": data.get("params") or {}}
    except Exception:
        logger.exception("Tool planner failed (non-fatal).")
        return none_result
