"""
AI orchestrator (Facade).

``handle_user_message`` is the single entry point the rest of the app codes
against (Decision 0.3). It hides the agent subsystem behind one call: load the
user's preferences, load recent history, run the Concierge, return the reply.

Keeping this facade stable means ``trips/views.py`` never changes as we add more
agents: the Concierge (Agent 1) produces the reply, then the Data Architect
(Agent 2) silently updates the user's preferences — both behind this one call.
"""

from __future__ import annotations

import logging

from django.contrib.auth.models import User

from agents import concierge, data_architect
from trips.models import ChatSession
from users.models import UserPreference

logger = logging.getLogger(__name__)

# How many recent messages to send as context (A1.6).
HISTORY_LIMIT = 20

# Friendly Romanian fallback shown if anything in the AI layer fails (A1.8).
FALLBACK_REPLY = (
    "Îmi pare rău, am întâmpinat o problemă tehnică și nu am putut genera un "
    "răspuns acum. Te rog încearcă din nou peste câteva momente."
)

# Shown specifically when the provider rejects us for rate limit / quota, so it
# doesn't look like a generic crash (common on free LLM tiers).
RATE_LIMIT_REPLY = (
    "Am atins temporar limita de utilizare a modelului AI (free tier). "
    "Te rog încearcă din nou mai târziu sau folosește un alt model/cheie."
)

_RATE_LIMIT_HINTS = ("429", "quota", "exhausted", "rate limit", "resourceexhausted")


def _is_rate_limit(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return any(hint in text for hint in _RATE_LIMIT_HINTS)


def handle_user_message(prompt: str, session: ChatSession, user: User) -> str:
    """Return the assistant's reply text.

    Side effect: updates the user's ``UserPreference`` (Agent 2). Never raises —
    a Concierge failure returns :data:`FALLBACK_REPLY`; a Data Architect failure
    is swallowed so it can't replace a good reply.
    """
    try:
        preferences, _ = UserPreference.objects.get_or_create(user=user)

        # The user's current turn is already persisted by the view, so this
        # history ends with `prompt`. Take the last N, back to chronological.
        recent = list(session.messages.order_by("-sent_at", "-id")[:HISTORY_LIMIT])
        history = list(reversed(recent))

        reply = concierge.generate_reply(prompt, history, preferences)
    except Exception as exc:
        logger.exception("Concierge failed for user=%s session=%s", user.pk, session.pk)
        return RATE_LIMIT_REPLY if _is_rate_limit(exc) else FALLBACK_REPLY

    # Agent 2 runs synchronously but best-effort (A2.6): the user already has a
    # valid reply, so extraction must never break the chat.
    _update_preferences(history, preferences, user)
    return reply


def _update_preferences(history, preferences, user: User) -> None:
    """Run the Data Architect and persist any inferred preference changes."""
    try:
        validated = data_architect.extract_preferences(history)
        changed = data_architect.merge_preferences(preferences, validated)
        if changed:
            preferences.save(update_fields=changed)
            # TODO (blocker A2.5/C2.2): once Branch C adds `ai_updated_fields`
            # to UserPreference, record `changed` + timestamps there.
            logger.info("Data Architect updated %s for user=%s", changed, user.pk)
    except Exception:
        logger.exception("Data Architect failed (non-fatal) for user=%s", user.pk)
