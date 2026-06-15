"""
Automated tests for the AI agents (Branch A).

These run fully offline: the LLM is replaced by a fake/echo strategy, so no API
key or network is needed. The provider-agnostic Strategy interface is exactly
what makes this dependency injection possible.
"""

from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase

from agents import concierge, orchestrator
from agents.llm_client import (
    AnthropicClient,
    EchoClient,
    GeminiClient,
    LLMClient,
    make_llm_client,
)


class RecordingClient(LLMClient):
    """A fake strategy that records its inputs and returns a canned reply."""

    def __init__(self, reply="reply-fix"):
        self.reply = reply
        self.messages = None
        self.system = None

    def complete(self, messages, system):
        self.messages = messages
        self.system = system
        return self.reply


# --------------------------------------------------------------------------- #
# Strategy: EchoClient (offline fallback)
# --------------------------------------------------------------------------- #
class EchoClientTests(SimpleTestCase):
    def test_echoes_last_user_message(self):
        reply = EchoClient().complete(
            [{"role": "user", "content": "Vreau în Roma"}], system="x"
        )
        self.assertIsInstance(reply, str)
        self.assertIn("Vreau în Roma", reply)


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #
class FactoryTests(SimpleTestCase):
    def test_falls_back_to_echo_without_key(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertIsInstance(make_llm_client("anthropic"), EchoClient)

    def test_unknown_provider_falls_back_to_echo(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertIsInstance(make_llm_client("does-not-exist"), EchoClient)

    def test_placeholder_key_is_treated_as_missing(self):
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "replace-me"}, clear=True):
            self.assertIsInstance(make_llm_client("anthropic"), EchoClient)

    def test_returns_anthropic_when_key_and_sdk_present(self):
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}, clear=True), \
                mock.patch("agents.llm_client._module_available", return_value=True):
            self.assertIsInstance(make_llm_client("anthropic"), AnthropicClient)

    def test_returns_gemini_when_key_and_sdk_present(self):
        with mock.patch.dict("os.environ", {"GOOGLE_API_KEY": "g-test"}, clear=True), \
                mock.patch("agents.llm_client._module_available", return_value=True):
            self.assertIsInstance(make_llm_client("gemini"), GeminiClient)


# --------------------------------------------------------------------------- #
# Concierge agent
# --------------------------------------------------------------------------- #
class ConciergeTests(SimpleTestCase):
    def _prefs(self, **kw):
        defaults = dict(
            dietary_preference="", hotel_stars=None, travel_pace="",
            budget=None, interests="",
        )
        defaults.update(kw)
        return SimpleNamespace(**defaults)

    def test_uses_injected_client_and_returns_its_reply(self):
        client = RecordingClient(reply="salut!")
        history = [SimpleNamespace(role="user", content="Bună")]
        out = concierge.generate_reply("Bună", history, self._prefs(), client=client)
        self.assertEqual(out, "salut!")

    def test_history_is_mapped_to_role_content_dicts(self):
        client = RecordingClient()
        history = [
            SimpleNamespace(role="user", content="Vreau la mare"),
            SimpleNamespace(role="assistant", content="Unde anume?"),
        ]
        concierge.generate_reply("...", history, self._prefs(), client=client)
        self.assertEqual(
            client.messages,
            [
                {"role": "user", "content": "Vreau la mare"},
                {"role": "assistant", "content": "Unde anume?"},
            ],
        )

    def test_preferences_are_rendered_into_system_prompt(self):
        client = RecordingClient()
        prefs = self._prefs(interests="muzee, gastronomie", travel_pace="slow")
        concierge.generate_reply("x", [], prefs, client=client)
        self.assertIn("Preferințele utilizatorului", client.system)
        self.assertIn("muzee, gastronomie", client.system)
        self.assertIn("slow", client.system)

    def test_empty_history_falls_back_to_prompt(self):
        client = RecordingClient()
        concierge.generate_reply("doar prompt", [], self._prefs(), client=client)
        self.assertEqual(client.messages, [{"role": "user", "content": "doar prompt"}])


# --------------------------------------------------------------------------- #
# Orchestrator (Facade) — needs the DB
# --------------------------------------------------------------------------- #
class OrchestratorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ana", password="pw")
        from trips.models import ChatSession
        self.session = ChatSession.objects.create(user=self.user, title="t")

    def _add(self, role, content):
        from trips.models import ChatMessage
        return ChatMessage.objects.create(session=self.session, role=role, content=content)

    def test_returns_reply_offline(self):
        self._add("user", "Vreau la Veneția")
        reply = orchestrator.handle_user_message("Vreau la Veneția", self.session, self.user)
        self.assertIsInstance(reply, str)
        self.assertTrue(reply)

    def test_history_is_chronological_without_duplicating_prompt(self):
        self._add("user", "u1")
        self._add("assistant", "a1")
        self._add("user", "u2")  # current turn, already persisted by the view

        captured = {}

        def fake(prompt, history, preferences):
            captured["history"] = [(m.role, m.content) for m in history]
            return "ok"

        with mock.patch.object(concierge, "generate_reply", side_effect=fake):
            out = orchestrator.handle_user_message("u2", self.session, self.user)

        self.assertEqual(out, "ok")
        self.assertEqual(
            captured["history"],
            [("user", "u1"), ("assistant", "a1"), ("user", "u2")],
        )
        # the current prompt appears exactly once
        self.assertEqual(captured["history"].count(("user", "u2")), 1)

    def test_failure_returns_friendly_fallback(self):
        self._add("user", "boom")
        with mock.patch.object(concierge, "generate_reply", side_effect=RuntimeError("x")):
            reply = orchestrator.handle_user_message("boom", self.session, self.user)
        self.assertEqual(reply, orchestrator.FALLBACK_REPLY)
