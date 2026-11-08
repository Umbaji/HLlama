"""Moving a reminder she already has: which one, to when, and the move itself.

"Décale le rappel 2 à jeudi" was impossible: nothing could touch a reminder
that existed, so the request reached the model as a question and the model
answered from imagination.
"""
import json
import unittest
from datetime import datetime
from unittest import mock

from app.services import button_router, reminder_update
from app.services.chat_state import reminder_last_list, reminder_update_drafts
from app.services.structured_response import CHAT_RESPONSE_FORMAT
from app.utils.anonymity import pseudo_id_for

WA_ID = "22890000000"
PSEUDO = pseudo_id_for(WA_ID)
OLD_ID = "11111111-2222-4333-8444-555555555555"
NEW_ID = "66666666-7777-4888-9999-000000000000"
# The dates below are fixed; so is "now", or they fall into the past and the
# bot asks for another date (red from 2026-10-25 on).
NOW = datetime(2026, 10, 20, 9, 0)


class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body


def ok(data):
    return FakeResponse(200, {"status": 200, "error": False, "message": "OK", "data": data, "meta": None})


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


def listed_reminder(**overrides):
    """A reminder as the list she was shown."""
    reminder = {
        "id": OLD_ID,
        "kind": "pill",
        "message": "Prendre la pilule",
        "repeat_interval_days": None,
        "scheduled_at": "2026-10-21T20:00:00+00:00",
    }
    reminder.update(overrides)
    return reminder


def structured(**overrides):
    base = {
        "request_type": "reminder_update",
        "request_content": "décale le rappel 2 à jeudi",
        "reminder_number": 1,
        "scheduled_at": "2026-10-25T08:00:00",
        "reminder_kind": None,
        "repeat_interval_days": None,
    }
    base.update(overrides)
    return base


class ReminderUpdateTests(unittest.TestCase):
    def setUp(self):
        reminder_update_drafts.clear()
        reminder_last_list.clear()
        reminder_last_list.set(PSEUDO, [listed_reminder()])
        self.send = mock.Mock()
        clock = mock.patch("app.services.reminder_update.now_local", return_value=NOW)
        clock.start()
        self.addCleanup(clock.stop)

    def start(self, **overrides):
        reminder_update.start_from_structured(WA_ID, structured(**overrides), self.send)

    def test_the_recap_shows_the_old_and_the_new_date(self):
        self.start()
        body, buttons = sent(self.send)[0]
        self.assertIn("21/10/2026", body)
        self.assertIn("25/10/2026", body)
        self.assertEqual(buttons, [reminder_update.CONFIRM_ID, reminder_update.CANCEL_ID])

    def test_the_missing_number_is_asked(self):
        self.start(reminder_number=None)
        body, _ = sent(self.send)[0]
        self.assertIn("Lequel", body)

    def test_her_answer_resolves_the_reminder(self):
        self.start(reminder_number=None)
        reminder_update.consume_text(WA_ID, "1", self.send)
        body, _ = sent(self.send)[-1]
        self.assertIn("Je le décale ?", body)

    def test_the_missing_date_is_asked(self):
        self.start(scheduled_at=None)
        body, _ = sent(self.send)[0]
        self.assertIn("nouvelle date", body)

    def test_an_unknown_number_is_refused(self):
        self.start(reminder_number=7)
        body, _ = sent(self.send)[0]
        self.assertIn("Je ne vois pas de rappel", body)

    def test_annulating_changes_nothing(self):
        self.start()
        reminder_update.consume_text(WA_ID, "annuler", self.send)
        self.assertIsNone(reminder_update_drafts.get(PSEUDO))

    def test_the_new_reminder_is_created_before_the_old_one_is_cancelled(self):
        """She is never left without the reminder she asked for."""
        calls = []

        def post(path, payload, **kwargs):
            calls.append(path)
            if path.endswith("/cancel"):
                return ok(listed_reminder())
            return ok({"id": NEW_ID})

        self.start()
        with mock.patch("app.services.reminder_update.post_json", side_effect=post), \
                mock.patch(
                    "app.services.reminder_update.cancel_user_reminder",
                    side_effect=lambda wa_id, reminder_id: calls.append("cancel") or listed_reminder(),
                ) as cancel:
            reminder_update.handle_button(WA_ID, reminder_update.CONFIRM_ID, self.send)
        self.assertEqual(calls[0], "/api/bot/reminders")
        cancel.assert_called_once_with(WA_ID, OLD_ID)

    def test_the_kind_of_the_old_reminder_is_kept(self):
        reminder_last_list.set(PSEUDO, [listed_reminder(
            kind="injection", message="Faire l'injection",
        )])
        self.start()
        with mock.patch("app.services.reminder_update.post_json", return_value=ok({"id": NEW_ID})) as post, \
                mock.patch("app.services.reminder_update.cancel_user_reminder", return_value=listed_reminder()):
            reminder_update.handle_button(WA_ID, reminder_update.CONFIRM_ID, self.send)
        self.assertEqual(post.call_args.args[1]["kind"], "injection")

    def test_a_failed_creation_leaves_the_old_reminder_alone(self):
        with mock.patch("app.services.reminder_update.post_json", return_value=None), \
                mock.patch("app.services.reminder_update.cancel_user_reminder") as cancel:
            self.start()
            reminder_update.handle_button(WA_ID, reminder_update.CONFIRM_ID, self.send)
        cancel.assert_not_called()
        self.assertIn("momentanément indisponible", sent(self.send)[-1][0])

    def test_a_failed_cancellation_is_reported_honestly(self):
        with mock.patch("app.services.reminder_update.post_json", return_value=ok({"id": NEW_ID})), \
                mock.patch("app.services.reminder_update.cancel_user_reminder", return_value=None):
            self.start()
            reminder_update.handle_button(WA_ID, reminder_update.CONFIRM_ID, self.send)
        self.assertIn("tu as donc les deux", sent(self.send)[-1][0])


class ContractTests(unittest.TestCase):
    def test_the_request_type_is_in_the_schema(self):
        schema = CHAT_RESPONSE_FORMAT["json_schema"]["schema"]
        self.assertIn("reminder_update", schema["properties"]["request_type"]["enum"])
        self.assertIn("reminder_number", schema["properties"])
        self.assertIn("reminder_number", schema["required"])


if __name__ == "__main__":
    unittest.main()
