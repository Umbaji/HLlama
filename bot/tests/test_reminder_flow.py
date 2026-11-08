"""Scheduling a reminder from a conversation: slots, recap, creation."""
import json
import unittest
from datetime import datetime
from unittest import mock

from app.services import button_router, reminder_flow
from app.services.chat_state import reminder_drafts, reminder_snapshot
from app.services.structured_response import CHAT_RESPONSE_FORMAT
from app.utils.anonymity import pseudo_id_for

WA_ID = "22890000000"
PSEUDO = pseudo_id_for(WA_ID)
NOW = datetime(2026, 10, 20, 10, 30)
REMINDER_ID = "3f2b1c4d-5555-4666-8777-888899990000"


class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body


def ok(data, message="REMINDER_CREATED", status=201):
    return FakeResponse(status, {"status": status, "error": False, "message": message, "data": data, "meta": None})


def err(code, status=400):
    return FakeResponse(status, {"status": status, "error": True, "message": code, "data": None, "meta": None})


def sent(send):
    """[(body text, [button ids])] for each message passed to `send`."""
    out = []
    for call in send.call_args_list:
        payload = call.args[0]
        payload = json.loads(payload) if isinstance(payload, str) else payload
        if payload.get("type") == "interactive":
            interactive = payload["interactive"]
            ids = [b["reply"]["id"] for b in interactive["action"]["buttons"]]
            out.append((interactive["body"]["text"], ids))
        else:
            out.append((payload["text"]["body"], []))
    return out


def structured(**overrides):
    base = {
        "request_type": "reminder",
        "request_content": "prendre la pilule",
        "reminder_kind": "pill",
        "scheduled_at": "2026-10-21T20:00:00",
        "repeat_interval_days": None,
        "amount": None,
        "reason": None,
    }
    base.update(overrides)
    return base


class ReminderFlowTest(unittest.TestCase):
    def setUp(self):
        reminder_drafts.clear()
        self.posts = []
        self.replies = []

        def fake_post(path, body, **_):
            self.posts.append((path, body))
            return self.replies.pop(0) if self.replies else ok({"id": REMINDER_ID, "kind": body["kind"]})

        patcher = mock.patch.object(reminder_flow, "post_json", side_effect=fake_post)
        patcher.start()
        self.addCleanup(patcher.stop)

        clock = mock.patch.object(reminder_flow, "now_local", return_value=NOW)
        clock.start()
        self.addCleanup(clock.stop)

        self.send = mock.Mock()

    def start(self, **overrides):
        reminder_flow.start_from_structured(WA_ID, structured(**overrides), self.send)

    def reply(self, text):
        return reminder_flow.consume_text(WA_ID, text, self.send)

    # -- the contract the model must fill -------------------------------

    def test_the_schema_carries_the_reminder_kind(self):
        schema = CHAT_RESPONSE_FORMAT["json_schema"]["schema"]
        self.assertIn("reminder_kind", schema["properties"])
        self.assertIn("reminder_kind", schema["required"])
        self.assertIn("pill", schema["properties"]["reminder_kind"]["enum"])

    # -- nothing is created before she confirms -------------------------

    def test_a_complete_reminder_only_recaps_first(self):
        self.start()
        self.assertEqual(self.posts, [])
        text, buttons = sent(self.send)[0]
        self.assertIn("Rappel pilule le 21/10/2026 à 20:00", text)
        self.assertEqual(buttons, [reminder_flow.CONFIRM_ID, reminder_flow.CANCEL_ID])

    def test_confirming_creates_it_with_its_kind(self):
        self.start()
        button_router.route_button_reply(WA_ID, reminder_flow.CONFIRM_ID, self.send)
        self.assertEqual(self.posts, [("/api/bot/reminders", {
            "pseudo_id": PSEUDO,
            "telnumber": WA_ID,
            "kind": "pill",
            "message": "prendre la pilule",
            "scheduled_at": "2026-10-21T20:00:00",
            "repeat_interval_days": None,
        })])
        self.assertIn("✅ Rappel programmé le 21/10/2026 à 20:00", sent(self.send)[-1][0])
        self.assertIsNone(reminder_drafts.get(PSEUDO))

    def test_creating_drops_the_snapshot_the_model_is_shown(self):
        """Otherwise her next message is answered from a note that predates the
        reminder she has just confirmed."""
        reminder_snapshot.set(PSEUDO, [])
        self.start()
        button_router.route_button_reply(WA_ID, reminder_flow.CONFIRM_ID, self.send)
        self.assertIsNone(reminder_snapshot.get(PSEUDO))

    def test_cancelling_the_recap_creates_nothing(self):
        self.start()
        button_router.route_button_reply(WA_ID, reminder_flow.CANCEL_ID, self.send)
        self.assertEqual(self.posts, [])
        self.assertEqual(sent(self.send)[-1][0], reminder_flow.CANCELLED_TEXT)

    def test_a_confirm_button_without_a_draft_says_so(self):
        button_router.route_button_reply(WA_ID, reminder_flow.CONFIRM_ID, self.send)
        self.assertEqual(self.posts, [])
        self.assertEqual(sent(self.send)[-1][0], reminder_flow.GAVE_UP_TEXT)

    def test_an_unknown_kind_falls_back_to_other(self):
        self.start(reminder_kind="birthday")
        self.reply("oui")
        self.assertEqual(self.posts[0][1]["kind"], "other")

    # -- the date she types ---------------------------------------------

    def test_a_missing_date_is_asked_and_parsed_from_her_words(self):
        self.start(scheduled_at=None)
        self.assertEqual(sent(self.send)[0][0], reminder_flow.QUESTIONS["when"])
        self.assertTrue(self.reply("demain à 20h"))
        self.assertIn("le 21/10/2026 à 20:00", sent(self.send)[-1][0])
        self.reply("oui")
        self.assertEqual(self.posts[0][1]["scheduled_at"], "2026-10-21T20:00:00")

    def test_a_date_already_past_is_asked_again(self):
        self.start(scheduled_at="2026-10-01T08:00:00")
        self.assertEqual(sent(self.send)[0][0], reminder_flow.QUESTIONS["when"])

    def test_an_unreadable_date_is_asked_again_then_given_up(self):
        self.start(scheduled_at=None)
        for _ in range(2):
            self.assertTrue(self.reply("quand tu veux"))
        self.assertEqual(sent(self.send)[-1][0], reminder_flow.INVALID_TEXTS["when"])
        self.assertTrue(self.reply("quand tu veux"))
        self.assertEqual(sent(self.send)[-1][0], reminder_flow.GAVE_UP_TEXT)
        self.assertIsNone(reminder_drafts.get(PSEUDO))

    def test_a_missing_message_is_asked_first(self):
        self.start(request_content=None)
        self.assertEqual(sent(self.send)[0][0], reminder_flow.QUESTIONS["message"])
        self.reply("prendre mon traitement")
        self.assertIn("« prendre mon traitement »", sent(self.send)[-1][0])

    def test_a_repeat_interval_is_kept_and_shown(self):
        self.start(repeat_interval_days=90, reminder_kind="injection")
        self.assertIn("Répété tous les 90 jours", sent(self.send)[0][0])
        self.reply("oui")
        self.assertEqual(self.posts[0][1]["repeat_interval_days"], 90)

    def test_an_out_of_range_repeat_is_dropped(self):
        self.start(repeat_interval_days=0)
        self.reply("oui")
        self.assertIsNone(self.posts[0][1]["repeat_interval_days"])

    # -- how often it comes back -----------------------------------------

    def test_a_weekly_pattern_is_one_reminder_the_backend_repeats(self):
        self.start(repeat_pattern="weekly")
        self.assertIn("Répété toutes les semaines", sent(self.send)[0][0])
        self.reply("oui")
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.posts[0][1]["repeat_interval_days"], 7)

    def test_a_daily_pattern_is_one_reminder_the_backend_repeats(self):
        self.start(repeat_pattern="daily")
        self.reply("oui")
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.posts[0][1]["repeat_interval_days"], 1)

    def test_a_monthly_pattern_is_a_series_of_dated_reminders(self):
        """A month is not a number of days: the bot creates them one by one."""
        self.start(repeat_pattern="monthly", scheduled_at="2026-10-21T20:00:00")
        self.assertIn("Répété chaque mois", sent(self.send)[0][0])
        self.reply("oui")
        self.assertEqual(len(self.posts), 6)
        self.assertEqual(
            [post[1]["scheduled_at"] for post in self.posts],
            [
                "2026-10-21T20:00:00", "2026-11-21T20:00:00", "2026-12-21T20:00:00",
                "2027-01-21T20:00:00", "2027-02-21T20:00:00", "2027-03-21T20:00:00",
            ],
        )
        self.assertIsNone(self.posts[0][1]["repeat_interval_days"])

    def test_a_series_that_fails_halfway_says_how_many_exist(self):
        self.replies.extend([ok({"id": REMINDER_ID}), ok({"id": REMINDER_ID}), None])
        self.start(repeat_pattern="monthly")
        self.reply("oui")
        self.assertEqual(len(self.posts), 3)
        self.assertIn("2 fois sur 6", sent(self.send)[-1][0])

    def test_an_unknown_pattern_is_ignored(self):
        self.start(repeat_pattern="yearly")
        self.reply("oui")
        self.assertEqual(len(self.posts), 1)
        self.assertIsNone(self.posts[0][1]["repeat_interval_days"])

    # -- her words during the flow --------------------------------------

    def test_annuler_drops_the_draft_only(self):
        self.start(scheduled_at=None)
        self.assertTrue(self.reply("annuler"))
        self.assertEqual(sent(self.send)[-1][0], reminder_flow.CANCELLED_TEXT)
        self.assertIsNone(reminder_drafts.get(PSEUDO))
        self.assertEqual(self.posts, [])

    def test_a_message_outside_a_draft_is_not_consumed(self):
        self.assertFalse(self.reply("bonjour"))

    def test_another_question_during_the_recap_goes_to_the_model(self):
        self.start()
        self.assertFalse(self.reply("c'est quoi la pilule du lendemain ?"))
        self.assertEqual(self.posts, [])

    # -- what the backend answers ---------------------------------------

    def test_reminder_in_past_asks_the_date_again(self):
        self.replies.append(err("REMINDER_IN_PAST"))
        self.start()
        self.reply("oui")
        self.assertIn(reminder_flow.PAST_TEXT, sent(self.send)[-1][0])
        self.assertIsNotNone(reminder_drafts.get(PSEUDO))
        self.assertTrue(self.reply("dans 3 jours"))
        self.reply("oui")
        self.assertEqual(self.posts[-1][1]["scheduled_at"], "2026-10-23T10:30:00")

    def test_a_backend_failure_says_so_and_forgets_the_draft(self):
        self.replies.append(err("INTERNAL_ERROR", 500))
        self.start()
        self.reply("oui")
        self.assertEqual(sent(self.send)[-1][0], reminder_flow.UNAVAILABLE_TEXT)
        self.assertIsNone(reminder_drafts.get(PSEUDO))

    def test_an_unreachable_backend_says_so(self):
        self.replies.append(None)
        self.start()
        self.reply("oui")
        self.assertEqual(sent(self.send)[-1][0], reminder_flow.UNAVAILABLE_TEXT)


if __name__ == "__main__":
    unittest.main()
