import json
import unittest

from app.services import consent_hold, helplines, intents, menu
from app.services.chat_state import (
    awaiting_her_answer,
    consent_prompt_seen,
    feedback_comment_pending,
    health_fact_drafts,
    held_request,
    pending_place_category,
)
from app.utils import consent_gate
from app.utils.anonymity import pseudo_id_for

WA_ID = "22890000000"
CONFIRMATIONS = ("J'ai donne mon consentement ✅",)


class MenuEntries(unittest.TestCase):
    """An entry acts. It used to answer "Écrivez « numéros verts »", asking a
    woman who had just chosen from a menu to type what she had chosen."""

    def _sent(self, number):
        sent = []
        self.assertTrue(menu.act(WA_ID, number, sent.append))
        return sent[0]

    def test_every_entry_does_something(self):
        for number in ("1", "2", "3", "4"):
            with self.subTest(number=number):
                self.assertTrue(self._sent(number))

    def test_the_helplines_are_sent_not_described(self):
        payload = json.loads(self._sent("4"))["text"]["body"]

        for line in helplines.load().values():
            self.assertIn(line["number"], payload)
        self.assertNotIn("Écrivez", payload)

    def test_finding_a_place_offers_the_two_choices(self):
        payload = self._sent("3")

        self.assertEqual(payload["interactive"]["type"], "button")
        titles = [b["reply"]["title"] for b in payload["interactive"]["action"]["buttons"]]
        self.assertEqual(titles, ["Pharmacie", "Clinique"])

    def test_choosing_a_place_remembers_it_and_asks_for_the_location(self):
        sent = []
        menu.handle_menu_button(WA_ID, f"{menu.BUTTON_PREFIX}3:clinic", sent.append)

        self.assertEqual(pending_place_category.get(WA_ID), "clinic")
        self.assertIn("position", json.loads(sent[0])["text"]["body"])

    def test_no_entry_tells_her_to_retype_what_she_chose(self):
        for number in ("1", "2", "3", "4"):
            with self.subTest(number=number):
                payload = self._sent(number)
                body = payload if isinstance(payload, dict) else json.loads(payload)["text"]["body"]
                self.assertNotIn("Écrivez «", str(body))

    def test_the_numbers_she_may_type(self):
        for text in ("4", "4.", "4)", " 4 ", "1⃣", "1️⃣"):
            with self.subTest(text=text):
                self.assertIsNotNone(menu.number_in(text))

    def test_what_is_not_a_menu_number(self):
        for text in ("5", "7", "0", "60", "menu", "6 pilules", "", None):
            with self.subTest(text=text):
                self.assertIsNone(menu.number_in(text))


class TypedIntents(unittest.TestCase):
    """Typing it and picking it from the menu must lead to the same place."""

    def test_the_words_that_reach_a_feature(self):
        cases = {
            "Numéro vert": intents.HELPLINES,
            "numéros verts": intents.HELPLINES,
            "NUMEROS VERTS": intents.HELPLINES,
            "ligne verte": intents.HELPLINES,
            "menu": intents.MENU,
            "aide": intents.MENU,
            "?": intents.MENU,
            "pharmacie": intents.PHARMACY,
            "une pharmacie": intents.PHARMACY,
            "clinique": intents.CLINIC,
            "centre de santé": intents.CLINIC,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(intents.detect(text), expected)

    def test_a_sentence_is_left_to_the_model(self):
        """A command is a word or two; a question is for the model."""
        for text in (
            "est-ce que je peux avoir un rendez-vous à la clinique ?",
            "j'ai mal au ventre depuis trois jours",
            "combien coûte une pharmacie de garde le dimanche soir chez nous",
        ):
            with self.subTest(text=text):
                self.assertIsNone(intents.detect(text))

    def test_a_typed_intent_is_served_like_the_menu_entry(self):
        typed, tapped = [], []
        menu.act_on_intent(WA_ID, intents.HELPLINES, typed.append)
        menu.act(WA_ID, "4", tapped.append)

        self.assertEqual(typed, tapped)

    def test_naming_the_place_skips_the_question(self):
        sent = []
        menu.act_on_intent(WA_ID, intents.PHARMACY, sent.append)

        self.assertEqual(pending_place_category.get(WA_ID), "pharmacy")
        self.assertIn("position", json.loads(sent[0])["text"]["body"])


class HeldRequest(unittest.TestCase):
    """A request the consent gate turned away comes back after consent,
    instead of being lost and retyped."""

    def setUp(self):
        held_request.pop(pseudo_id_for(WA_ID))
        self.sent = []
        self.handled = []

    def _text(self, body):
        return {"type": "text", "text": {"body": body}}

    def test_a_request_survives_the_consent_gate(self):
        kept = consent_hold.hold(WA_ID, self._text("Envoie 2000 F à 90000100"), CONFIRMATIONS)
        replayed = consent_hold.replay(WA_ID, self.sent.append, self.handled.append)

        self.assertTrue(kept)
        self.assertTrue(replayed)
        self.assertEqual(self.handled, ["Envoie 2000 F à 90000100"])
        self.assertIn("Envoie 2000 F", self.sent[0])

    def test_it_is_replayed_once_only(self):
        consent_hold.hold(WA_ID, self._text("ma question"), CONFIRMATIONS)
        consent_hold.replay(WA_ID, self.sent.append, self.handled.append)

        self.assertFalse(consent_hold.replay(WA_ID, self.sent.append, self.handled.append))
        self.assertEqual(len(self.handled), 1)

    def test_nothing_to_replay_is_not_an_event(self):
        self.assertFalse(consent_hold.replay(WA_ID, self.sent.append, self.handled.append))
        self.assertEqual(self.sent, [])

    def test_the_consent_confirmation_is_never_kept(self):
        """It would otherwise be replayed at her as if it were a request."""
        self.assertFalse(consent_hold.hold(WA_ID, self._text(CONFIRMATIONS[0]), CONFIRMATIONS))

    def test_only_text_is_kept(self):
        """A location or a voice note means nothing once its moment has passed."""
        for message in ({"type": "location"}, {"type": "audio"}, {"type": "text", "text": {"body": "  "}}):
            with self.subTest(message=message):
                self.assertFalse(consent_hold.hold(WA_ID, message, CONFIRMATIONS))

    def test_a_long_request_is_bounded(self):
        consent_hold.hold(WA_ID, self._text("x" * 5000), CONFIRMATIONS)
        consent_hold.replay(WA_ID, self.sent.append, self.handled.append)

        self.assertEqual(len(self.handled[0]), consent_hold.MAX_CHARS)

    def test_a_failure_while_replaying_does_not_escape(self):
        """Her request is worth trying; a crash in the handler is not worth
        losing the rest of the conversation over."""
        consent_hold.hold(WA_ID, self._text("ma question"), CONFIRMATIONS)

        def explode(_body):
            raise RuntimeError("model down")

        self.assertTrue(consent_hold.replay(WA_ID, self.sent.append, explode))



class InteractiveMenu(unittest.TestCase):
    """The menu is a native WhatsApp list: she taps instead of reading six
    lines, remembering a number and typing it."""

    def test_the_payload_respects_every_whatsapp_limit(self):
        payload = menu.build_payload(WA_ID)
        action = payload["interactive"]["action"]

        self.assertEqual(payload["interactive"]["type"], "list")
        self.assertLessEqual(len(action["button"]), 20)
        self.assertLessEqual(len(payload["interactive"]["header"]["text"]), 60)
        self.assertLessEqual(len(payload["interactive"]["footer"]["text"]), 60)
        rows = [row for section in action["sections"] for row in section["rows"]]
        self.assertLessEqual(len(rows), 10)
        for section in action["sections"]:
            self.assertLessEqual(len(section["title"]), 24)
        for row in rows:
            self.assertLessEqual(len(row["title"]), 24)
            self.assertLessEqual(len(row["description"]), 72)

    def test_every_entry_is_offered_once(self):
        rows = [
            row for section in menu.build_payload(WA_ID)["interactive"]["action"]["sections"]
            for row in section["rows"]
        ]
        ids = [row["id"] for row in rows]

        self.assertEqual(sorted(ids), [f"{menu.BUTTON_PREFIX}{n}" for n in range(1, 5)])
        self.assertEqual(len(set(ids)), len(ids))

    def test_tapping_an_entry_answers(self):
        sent = []
        menu.handle_menu_button(WA_ID, f"{menu.BUTTON_PREFIX}4", sent.append)

        self.assertTrue(sent[0])

    def test_the_text_fallback_covers_the_four_entries(self):
        """Sent when the list is refused, outside the 24h window for instance."""
        for number in range(1, 5):
            self.assertIn(f"*{number}.*", menu.TEXT_FALLBACK)


class ConsentPrompt(unittest.TestCase):
    """The first message a woman ever receives from HLlama."""

    def setUp(self):
        consent_prompt_seen.pop(pseudo_id_for(WA_ID))

    def test_it_introduces_hllama_before_asking(self):
        text = consent_gate._prompt_text(WA_ID)

        self.assertIn("Bonjour", text)
        self.assertIn("HLlama", text)
        self.assertIn("Umbaji", text)
        self.assertIn("libre", text)

    def test_the_next_ask_does_not_repeat_the_introduction(self):
        consent_gate._prompt_text(WA_ID)
        second = consent_gate._prompt_text(WA_ID)

        self.assertEqual(second, consent_gate.CONSENT_PROMPT_REPEAT_TEXT)
        self.assertNotIn("Bonjour", second)



class ShortcutsYieldToFlows(unittest.TestCase):
    """A question the bot asked comes first: her answer must not be read as a
    menu choice."""

    def setUp(self):
        health_fact_drafts.pop(pseudo_id_for(WA_ID))
        feedback_comment_pending.pop(pseudo_id_for(WA_ID))

    def test_nothing_pending_means_the_shortcuts_work(self):
        self.assertFalse(awaiting_her_answer(pseudo_id_for(WA_ID)))

    def test_a_health_fact_in_progress_holds_the_floor(self):
        """Asked to confirm a health fact, her answer is not a menu choice."""
        health_fact_drafts.set(pseudo_id_for(WA_ID), {"fact": "enceinte"})

        self.assertTrue(awaiting_her_answer(pseudo_id_for(WA_ID)))

    def test_a_pending_comment_holds_the_floor(self):
        """Her comment on the service may well be a single word."""
        feedback_comment_pending.set(pseudo_id_for(WA_ID))

        self.assertTrue(awaiting_her_answer(pseudo_id_for(WA_ID)))


if __name__ == "__main__":
    unittest.main()
