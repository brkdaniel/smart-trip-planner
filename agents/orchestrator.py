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
import threading

from django.conf import settings
from django.contrib.auth.models import User
from django.db import connection
from django.utils import timezone

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

    # Agent 2 is best-effort: the user already has a valid reply, so extraction
    # must never break the chat. By default it runs off the request path (A3.1).
    _run_data_architect(session, user)
    return reply


def _run_data_architect(session: ChatSession, user: User) -> None:
    """Run the Data Architect, async (A3.1) or inline depending on settings."""
    if getattr(settings, "AGENTS_RUN_ASYNC", True):
        threading.Thread(
            target=_update_preferences_threaded,
            args=(session, user),
            daemon=True,
        ).start()
    else:
        _update_preferences(session, user)


def _update_preferences_threaded(session: ChatSession, user: User) -> None:
    """Thread entry point for A3.1: run extraction, then release the DB connection."""
    try:
        _update_preferences(session, user)
    finally:
        # A new thread gets its own DB connection — close it or it leaks.
        connection.close()


def _update_preferences(session: ChatSession, user: User) -> None:
    """Run the Data Architect and persist any inferred preference changes.

    Self-contained (re-fetches its own context) so it is safe to run in a
    background thread on a fresh DB connection.
    """
    try:
        preferences, _ = UserPreference.objects.get_or_create(user=user)
        recent = list(session.messages.order_by("-sent_at", "-id")[:HISTORY_LIMIT])
        history = list(reversed(recent))

        validated = data_architect.extract_preferences(history)
        changed = data_architect.merge_preferences(preferences, validated)
        if not changed:
            return

        update_fields = list(changed)
        # A2.5/C2.2: stamp which fields the AI set (with timestamps) so the UI
        # can show an "inferred from chat" badge (C2.3).
        if _stamp_ai_fields(preferences, changed):
            update_fields.append("ai_updated_fields")

        preferences.save(update_fields=update_fields)
        logger.info("Data Architect updated %s for user=%s", changed, user.pk)
    except Exception:
        logger.exception("Data Architect failed (non-fatal) for user=%s", user.pk)


def _stamp_ai_fields(preferences, changed) -> bool:
    """Record an ISO timestamp per AI-updated field in ``ai_updated_fields``.

    Defensive: if the model doesn't have the field yet (Branch C migration not
    landed), it's a no-op and returns False. Returns True if it stamped.
    """
    if not hasattr(preferences, "ai_updated_fields"):
        return False
    stamps = dict(preferences.ai_updated_fields or {})
    now = timezone.now().isoformat()
    for field in changed:
        stamps[field] = now
    preferences.ai_updated_fields = stamps
    return True
