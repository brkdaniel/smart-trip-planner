"""
Automated tests for the AI agents (Branch A).

These run fully offline: the LLM is replaced by a fake/echo strategy, so no API
key or network is needed. The provider-agnostic Strategy interface is exactly
what makes this dependency injection possible.
"""

from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase

from agents import concierge, data_architect, orchestrator
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

    def test_returns_concierge_reply(self):
        self._add("user", "Vreau la Veneția")
        with mock.patch.object(concierge, "generate_reply", return_value="R"), \
                mock.patch.object(data_architect, "extract_preferences", return_value={}):
            reply = orchestrator.handle_user_message("Vreau la Veneția", self.session, self.user)
        self.assertEqual(reply, "R")

    def test_history_is_chronological_without_duplicating_prompt(self):
        self._add("user", "u1")
        self._add("assistant", "a1")
        self._add("user", "u2")  # current turn, already persisted by the view

        captured = {}

        def fake(prompt, history, preferences):
            captured["history"] = [(m.role, m.content) for m in history]
            return "ok"

        with mock.patch.object(concierge, "generate_reply", side_effect=fake), \
                mock.patch.object(data_architect, "extract_preferences", return_value={}):
            out = orchestrator.handle_user_message("u2", self.session, self.user)

        self.assertEqual(out, "ok")
        self.assertEqual(
            captured["history"],
            [("user", "u1"), ("assistant", "a1"), ("user", "u2")],
        )
        # the current prompt appears exactly once
        self.assertEqual(captured["history"].count(("user", "u2")), 1)

    def test_concierge_failure_returns_friendly_fallback(self):
        self._add("user", "boom")
        with mock.patch.object(concierge, "generate_reply", side_effect=RuntimeError("x")):
            reply = orchestrator.handle_user_message("boom", self.session, self.user)
        self.assertEqual(reply, orchestrator.FALLBACK_REPLY)

    def test_data_architect_failure_does_not_break_reply(self):
        self._add("user", "boom")
        with mock.patch.object(concierge, "generate_reply", return_value="R"), \
                mock.patch.object(data_architect, "extract_preferences", side_effect=RuntimeError("x")):
            reply = orchestrator.handle_user_message("boom", self.session, self.user)
        self.assertEqual(reply, "R")  # Concierge reply preserved (A2.6)

    def test_data_architect_persists_inferred_preferences(self):
        self._add("user", "vreau hotel de 5 stele")
        with mock.patch.object(concierge, "generate_reply", return_value="R"), \
                mock.patch.object(data_architect, "extract_preferences", return_value={"hotel_stars": 5}):
            orchestrator.handle_user_message("vreau hotel de 5 stele", self.session, self.user)
        self.user.preferences.refresh_from_db()
        self.assertEqual(self.user.preferences.hotel_stars, 5)


class OrchestratorHelperTests(SimpleTestCase):
    def test_detects_rate_limit_errors(self):
        self.assertTrue(orchestrator._is_rate_limit(RuntimeError("429 quota exceeded")))
        self.assertTrue(orchestrator._is_rate_limit(Exception("ResourceExhausted")))

    def test_other_errors_are_not_rate_limit(self):
        self.assertFalse(orchestrator._is_rate_limit(ValueError("bad json")))


# --------------------------------------------------------------------------- #
# Data Architect — extraction + validation (offline)
# --------------------------------------------------------------------------- #
class DataArchitectExtractionTests(SimpleTestCase):
    def test_strips_code_fences_and_parses(self):
        client = RecordingClient(reply='```json\n{"hotel_stars": 4}\n```')
        out = data_architect.extract_preferences([], client=client)
        self.assertEqual(out, {"hotel_stars": 4})

    def test_malformed_json_returns_empty(self):
        client = RecordingClient(reply="îmi pare rău, nu pot")
        self.assertEqual(data_architect.extract_preferences([], client=client), {})


class ValidationTests(SimpleTestCase):
    def test_drops_unknown_keys(self):
        out = data_architect.validate({"hotel_stars": 3, "evil": "x", "country": "IT"})
        self.assertEqual(out, {"hotel_stars": 3})

    def test_hotel_stars_clamped_to_1_5(self):
        self.assertNotIn("hotel_stars", data_architect.validate({"hotel_stars": 6}))
        self.assertNotIn("hotel_stars", data_architect.validate({"hotel_stars": 0}))
        self.assertNotIn("hotel_stars", data_architect.validate({"hotel_stars": "abc"}))
        self.assertEqual(data_architect.validate({"hotel_stars": 4})["hotel_stars"], 4)

    def test_travel_pace_validated_and_mapped(self):
        self.assertNotIn("travel_pace", data_architect.validate({"travel_pace": "turbo"}))
        self.assertEqual(data_architect.validate({"travel_pace": "relaxat"})["travel_pace"], "slow")
        self.assertEqual(data_architect.validate({"travel_pace": "FAST"})["travel_pace"], "fast")

    def test_budget_coerced_to_positive_decimal(self):
        self.assertEqual(data_architect.validate({"budget": "800"})["budget"], Decimal("800"))
        self.assertNotIn("budget", data_architect.validate({"budget": -5}))
        self.assertNotIn("budget", data_architect.validate({"budget": "lots"}))

    def test_interests_list_joined_and_empty_dropped(self):
        self.assertEqual(
            data_architect.validate({"interests": ["muzee", "plajă"]})["interests"],
            "muzee, plajă",
        )
        self.assertNotIn("interests", data_architect.validate({"interests": "   "}))

    def test_nulls_are_dropped(self):
        out = data_architect.validate(
            {"dietary_preference": None, "hotel_stars": None, "travel_pace": None,
             "budget": None, "interests": None}
        )
        self.assertEqual(out, {})


# --------------------------------------------------------------------------- #
# Data Architect — merge strategy (offline)
# --------------------------------------------------------------------------- #
class MergeTests(SimpleTestCase):
    def _prefs(self):
        return SimpleNamespace(
            dietary_preference="", hotel_stars=3, travel_pace="medium",
            budget=None, interests="",
        )

    def test_overwrites_differing_value(self):
        prefs = self._prefs()
        changed = data_architect.merge_preferences(prefs, {"hotel_stars": 5})
        self.assertEqual(changed, ["hotel_stars"])
        self.assertEqual(prefs.hotel_stars, 5)

    def test_skips_equal_value(self):
        prefs = self._prefs()
        changed = data_architect.merge_preferences(prefs, {"travel_pace": "medium"})
        self.assertEqual(changed, [])
        self.assertEqual(prefs.travel_pace, "medium")

    def test_never_nulls_out_existing(self):
        prefs = self._prefs()
        prefs.interests = "ski"
        changed = data_architect.merge_preferences(prefs, {})  # nothing inferred
        self.assertEqual(changed, [])
        self.assertEqual(prefs.interests, "ski")

    def test_reports_all_changed_fields(self):
        prefs = self._prefs()
        changed = data_architect.merge_preferences(
            prefs, {"hotel_stars": 4, "interests": "muzee", "travel_pace": "slow"}
        )
        self.assertEqual(set(changed), {"hotel_stars", "interests", "travel_pace"})
