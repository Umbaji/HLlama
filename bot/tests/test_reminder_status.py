import json
import unittest
from unittest import mock

from app.services.chat_state import reminder_last_list, reminder_snapshot
from app.services.reminder_status import (
    build_list_payload,
    cancel_user_reminder,
    extract_cancel_number,
    fetch_user_reminders,
    forget_snapshot,
    handle_button,
    handle_cancel_one,
    handle_list_request,
    is_detail_request,
    is_list_request,
    snapshot,
)
from app.utils.anonymity import pseudo_id_for

WA_ID = "22890000000"
PSEUDO = pseudo_id_for(WA_ID)
R1 = "7d1c2a4e-1111-4222-8333-944455556666"
R2 = "0b6f7c1a-aaaa-4bbb-8ccc-dddd00001111"


def reminder(rid=R1, kind="pill", days=1):
    return {
        "id": rid,
        "kind": kind,
        "message": "Prendre la pilule",
        "scheduled_at": "2026-09-25T08:00:00+00:00",
    }


class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body


def ok(data):
    return FakeResponse(200, {"status": 200, "error": False, "message": "OK", "data": data})


def as_dict(payload):
    return json.loads(payload) if isinstance(payload, str) else payload


def captured(send):
    texts = []
    for call in send.call_args_list:
        payload = as_dict(call.args[0])
        body = payload.get("text", {}).get("body") or payload.get("interactive", {}).get("body", {}).get("text", "")
        texts.append(body)
    return "\n".join(texts)


class ListDetectionTests(unittest.TestCase):
    def test_recognised_french_variants(self):
        for text in (
            "mes rappels",
            "quels sont mes rappels",
            "rappels en attente",
            "liste de mes rappels",
            "Quels sont mes rappels ?",
            "tous mes rappels",
        ):
            self.assertTrue(is_list_request(text), text)

    def test_not_a_list_request(self):
        for text in ("annule tout", "stop", "rappelle-moi demain", "quel est mon prochain rendez-vous", "mes rappels pour demain"):
            self.assertFalse(is_list_request(text), text)


class CancelNumberTests(unittest.TestCase):
    def test_extracts_the_number(self):
        self.assertEqual(extract_cancel_number("annule le rappel 2"), 2)
        self.assertEqual(extract_cancel_number("Annuler le rappel numéro 3"), 3)
        self.assertEqual(extract_cancel_number("annule le rappel 1 svp"), 1)

    def test_ignores_bare_opt_out_and_other_text(self):
        for text in ("annule", "annuler tout", "stop", "annule le rappel", "parle-moi des rappels"):
            self.assertIsNone(extract_cancel_number(text), text)


class FetchAndListTests(unittest.TestCase):
    def setUp(self):
        reminder_last_list.clear()

    def test_fetch_uses_pseudo_id_url_only(self):
        with mock.patch(
            "app.services.reminder_status.get_json",
            return_value=ok([reminder()]),
        ) as get:
            result = fetch_user_reminders(WA_ID)
        self.assertEqual(len(result), 1)
        path, kwargs = get.call_args
        self.assertEqual(path[0], f"/api/bot/users/{PSEUDO}/reminders")
        self.assertTrue("2289" not in path[0])

    def test_fetch_failure_returns_none_not_fabricated(self):
        with mock.patch("app.services.reminder_status.get_json", return_value=None):
            self.assertIsNone(fetch_user_reminders(WA_ID))
        with mock.patch("app.services.reminder_status.get_json", return_value=FakeResponse(500, {})):
            self.assertIsNone(fetch_user_reminders(WA_ID))

    def test_fetch_rejects_unwrapped_non_list_body(self):
        with mock.patch("app.services.reminder_status.get_json", return_value=ok({"nope": 1})):
            self.assertIsNone(fetch_user_reminders(WA_ID))

    def test_list_with_reminders_sets_cached_map_and_buttons(self):
        payload = as_dict(build_list_payload(WA_ID, [reminder()]))
        self.assertTrue(payload["type"] == "interactive")
        text = payload["interactive"]["body"]["text"]
        self.assertIn("Pilule", text)
        self.assertIn("25/09/2026", text)
        ids = [b["reply"]["id"] for b in payload["interactive"]["action"]["buttons"]]
        self.assertEqual(ids, [f"REM:CANCEL:{R1}"])
        cached = reminder_last_list.get(PSEUDO)
        self.assertEqual(cached[0]["id"], R1)

    def test_list_without_reminders_is_factual(self):
        payload = as_dict(build_list_payload(WA_ID, []))
        self.assertEqual(payload["text"]["body"], "Vous n'avez aucun rappel en attente.")

    def test_list_over_three_has_no_buttons_but_footer(self):
        reminders = [reminder(rid=f"{i}-0000", days=i) for i in range(1, 5)]
        payload = as_dict(build_list_payload(WA_ID, reminders))
        self.assertEqual(payload["type"], "text")
        self.assertIn("rappels en attente", payload["text"]["body"])
        self.assertIn("annule le rappel <numéro>", payload["text"]["body"])

    def test_the_kind_is_named_on_the_line(self):
        payload = as_dict(build_list_payload(WA_ID, [reminder(kind="appointment")]))
        self.assertIn("Rendez-vous", payload["interactive"]["body"]["text"])

    def test_list_unavailable_says_so(self):
        send = mock.Mock()
        with mock.patch("app.services.reminder_status.fetch_user_reminders", return_value=None):
            text = handle_list_request(WA_ID, send)
        sent = captured(send)
        self.assertIn("je n'ai pas pu consulter", sent.lower())
        self.assertEqual(text, "Je n'ai pas pu consulter vos rappels (service momentanément indisponible). Réessayez dans quelques minutes.")


class SnapshotTests(unittest.TestCase):
    """The snapshot feeds the note given to the model, so a stale one would
    make it deny a reminder she has just created."""

    def setUp(self):
        reminder_snapshot.clear()

    def test_the_snapshot_is_read_once_then_served_from_the_cache(self):
        with mock.patch(
            "app.services.reminder_status.get_json", return_value=ok([reminder()])
        ) as get:
            first = snapshot(WA_ID)
            second = snapshot(WA_ID)
        self.assertEqual(first, second)
        self.assertEqual(get.call_count, 1)

    def test_an_unreachable_backend_is_not_cached_and_stays_unknown(self):
        with mock.patch("app.services.reminder_status.get_json", return_value=None) as get:
            self.assertIsNone(snapshot(WA_ID))
            self.assertIsNone(snapshot(WA_ID))
        self.assertEqual(get.call_count, 2)

    def test_an_empty_list_is_cached_and_stays_distinct_from_unknown(self):
        with mock.patch("app.services.reminder_status.get_json", return_value=ok([])) as get:
            self.assertEqual(snapshot(WA_ID), [])
            self.assertEqual(snapshot(WA_ID), [])
        self.assertEqual(get.call_count, 1)

    def test_a_cancellation_drops_the_snapshot(self):
        reminder_snapshot.set(PSEUDO, [reminder()])
        with mock.patch("app.services.reminder_status.post_json", return_value=ok(reminder())):
            cancel_user_reminder(WA_ID, R1)
        self.assertIsNone(reminder_snapshot.get(PSEUDO))

    def test_forget_snapshot_is_enough_on_its_own(self):
        reminder_snapshot.set(PSEUDO, [reminder()])
        forget_snapshot(WA_ID)
        self.assertIsNone(reminder_snapshot.get(PSEUDO))


class CancelTests(unittest.TestCase):
    def setUp(self):
        reminder_last_list.clear()
        reminder_last_list.set(PSEUDO, [
            {"id": R1, "kind": "pill", "scheduled_at": "2026-09-25T08:00:00+00:00"},
            {"id": R2, "kind": "appointment", "scheduled_at": "2026-09-26T10:00:00+00:00"},
        ])

    def test_cancel_calls_backend_with_pseudo_id(self):
        with mock.patch(
            "app.services.reminder_status.post_json",
            return_value=ok(reminder()),
        ) as post:
            result = cancel_user_reminder(WA_ID, R1)
        self.assertIsNotNone(result)
        path, kwargs = post.call_args
        self.assertEqual(path[0], f"/api/bot/reminders/{R1}/cancel")
        self.assertEqual(path[1], {})
        self.assertEqual(kwargs["params"], {"pseudo_id": PSEUDO})

    def test_cancel_failure_is_apology_not_confirmation(self):
        send = mock.Mock()
        with mock.patch("app.services.reminder_status.cancel_user_reminder", return_value=None):
            handle_cancel_one(WA_ID, 1, send)
        self.assertIn("je n'ai pas pu annuler", captured(send).lower())

    def test_cancel_out_of_range_is_unknown(self):
        send = mock.Mock()
        with mock.patch("app.services.reminder_status.cancel_user_reminder") as cancel:
            handle_cancel_one(WA_ID, 5, send)
        cancel.assert_not_called()
        self.assertIn("je ne vois pas de rappel avec ce numéro", captured(send).lower())

    def test_cancel_confirms_with_kind_and_date(self):
        send = mock.Mock()
        with mock.patch(
            "app.services.reminder_status.cancel_user_reminder",
            return_value={
                "id": R2,
                "kind": "appointment",
                "scheduled_at": "2026-09-26T10:00:00+00:00",
            },
        ):
            handle_cancel_one(WA_ID, 2, send)
        self.assertIn("Rendez-vous", captured(send))
        self.assertIn("26/09/2026", captured(send))

    def test_button_cancels_by_raw_id(self):
        send = mock.Mock()
        with mock.patch(
            "app.services.reminder_status.cancel_user_reminder",
            return_value=reminder(R1),
        ) as cancel:
            handle_button(WA_ID, f"REM:CANCEL:{R1}", send)
        self.assertEqual(cancel.call_args.args[0], WA_ID)
        self.assertEqual(cancel.call_args.args[1], R1)
        self.assertIn("Pilule", captured(send))

    def test_she_can_ask_for_the_message_a_discreet_notice_announced(self):
        """"Vous avez un nouveau message de HLlama" says nothing; asking what
        it was used to reach the model, which redirected her to health."""
        for text in (
            "quel est le message ?",
            "Quel est le message",
            "c'est quoi le message ?",
            "quel message ?",
            "le message ?",
            "montre moi le message",
            "je ne vois pas le message",
        ):
            self.assertTrue(is_detail_request(text), text)

    def test_a_real_question_is_not_taken_for_the_detail_question(self):
        for text in (
            "quel est le message de ce traitement ?",
            "je ne vois pas le message de mon mari, que faire ?",
            "bonjour",
            "mes rappels",
            "",
        ):
            self.assertFalse(is_detail_request(text), text)

    def test_unknown_button_prefix_is_ignored(self):
        send = mock.Mock()
        with mock.patch("app.services.reminder_status.cancel_user_reminder") as cancel:
            handle_button(WA_ID, "PAY:nope", send)
        cancel.assert_not_called()
        send.assert_not_called()


if __name__ == "__main__":
    unittest.main()