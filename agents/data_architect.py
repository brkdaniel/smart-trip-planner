"""
Data Architect agent (Agent 2) — silent preference extraction.

Reads the conversation, asks the LLM (Gemini, per Decision 0.1) to return a
strict JSON object matching the ``UserPreference`` schema, then *never trusts it*:
the raw output is parsed, validated/coerced and merged conservatively into the
user's stored preferences.

Pipeline: :func:`extract_preferences` → :func:`validate` → :func:`merge_preferences`.
Each step is a pure function so it can be tested offline without an API key.
"""

from __future__ import annotations

import json
import logging
import re
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path

from agents.llm_client import LLMClient, make_llm_client

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent / "prompts" / "data_architect.md"

# Data Architect uses Gemini (Decision 0.1).
PROVIDER = "gemini"

# The only fields we accept; anything else from the LLM is dropped.
EXPECTED_KEYS = ("dietary_preference", "hotel_stars", "travel_pace", "budget", "interests")

VALID_PACES = {"slow", "medium", "fast"}
# Tolerant mapping in case the model answers in Romanian despite instructions.
_PACE_SYNONYMS = {
    "relaxat": "slow", "lejer": "slow", "lent": "slow",
    "normal": "medium", "echilibrat": "medium", "moderat": "medium",
    "intens": "fast", "alert": "fast", "rapid": "fast",
}

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


@lru_cache(maxsize=1)
def _load_system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _transcript(history) -> str:
    """Render ChatMessage objects into a plain-text transcript for extraction."""
    lines = [f"{m.role}: {m.content}" for m in history]
    return "\n".join(lines)


def _strip_code_fences(text: str) -> str:
    """Remove a leading ```json / ``` and a trailing ``` if the LLM wrapped it."""
    text = text.strip()
    text = _FENCE_RE.sub("", text)
    return text.strip()


def _parse_json(raw: str) -> dict:
    """Best-effort JSON parse. Returns {} on any problem (never raises)."""
    cleaned = _strip_code_fences(raw or "")
    if not cleaned:
        return {}
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Data Architect: JSON invalid, ignor extragerea.")
        return {}
    return data if isinstance(data, dict) else {}


def validate(data: dict) -> dict:
    """A2.3 — coerce/validate the parsed dict.

    Drops unknown keys, coerces types, discards invalid or null values. The
    result contains only clean, present values ready to merge.
    """
    if not isinstance(data, dict):
        return {}

    out: dict = {}

    diet = data.get("dietary_preference")
    if isinstance(diet, str) and diet.strip():
        out["dietary_preference"] = diet.strip()

    stars = data.get("hotel_stars")
    try:
        if stars is not None:
            stars = int(stars)
            if 1 <= stars <= 5:
                out["hotel_stars"] = stars
    except (TypeError, ValueError):
        pass

    pace = data.get("travel_pace")
    if isinstance(pace, str):
        pace = pace.strip().lower()
        pace = _PACE_SYNONYMS.get(pace, pace)
        if pace in VALID_PACES:
            out["travel_pace"] = pace

    budget = data.get("budget")
    if budget is not None:
        try:
            budget = Decimal(str(budget))
            if budget > 0:
                out["budget"] = budget
        except (InvalidOperation, ValueError):
            pass

    interests = data.get("interests")
    if isinstance(interests, list):  # tolerate a list, join it
        interests = ", ".join(str(i) for i in interests)
    if isinstance(interests, str) and interests.strip():
        out["interests"] = interests.strip()

    return out


def extract_preferences(history, client: LLMClient | None = None) -> dict:
    """A2.2 — extract validated preferences from the conversation.

    Returns a dict containing only clean, present values (possibly empty).
    Never raises.
    """
    client = client or make_llm_client(PROVIDER)
    system = _load_system_prompt()
    messages = [{
        "role": "user",
        "content": _transcript(history) + "\n\nExtrage preferințele ca JSON.",
    }]

    raw = client.complete(messages, system)
    return validate(_parse_json(raw))


def merge_preferences(preferences, validated: dict) -> list[str]:
    """A2.4 — merge validated values into a UserPreference. Returns changed fields.

    Conservative: only overwrites when the new value is present AND differs from
    the existing one. Never nulls-out an existing value (``validated`` already
    excludes nulls). Mutates ``preferences`` in place; the caller saves.
    """
    changed: list[str] = []
    for key in EXPECTED_KEYS:
        if key not in validated:
            continue
        new_value = validated[key]
        old_value = getattr(preferences, key, None)
        if new_value != old_value:
            setattr(preferences, key, new_value)
            changed.append(key)
    return changed
