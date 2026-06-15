"""
AI orchestrator (Facade).

``handle_user_message`` is the single entry point the rest of the app codes
against (Decision 0.3). It hides the agent subsystem behind one call: load the
user's preferences, load recent history, run the Concierge, return the reply.

Keeping this facade stable means ``trips/views.py`` never changes as we add more
agents — next week the Data Architect (Agent 2) slots in here, after the
Concierge reply, without touching the view.
"""

from __future__ import annotations

import logging

from django.contrib.auth.models import User

from agents import concierge
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


def handle_user_message(prompt: str, session: ChatSession, user: User) -> str:
    """Return the assistant's reply text.

    Side effect: may update UserPreference (once Agent 2 lands). Never raises —
    on any failure it logs and returns :data:`FALLBACK_REPLY` so the view/UI
    stays responsive.
    """
    try:
        preferences, _ = UserPreference.objects.get_or_create(user=user)

        # The user's current turn is already persisted by the view, so this
        # history ends with `prompt`. Take the last N, back to chronological.
        recent = list(session.messages.order_by("-sent_at", "-id")[:HISTORY_LIMIT])
        history = list(reversed(recent))

        return concierge.generate_reply(prompt, history, preferences)
    except Exception:
        logger.exception("AI orchestrator failed for user=%s session=%s", user.pk, session.pk)
        return FALLBACK_REPLY
