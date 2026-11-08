"""A fact she declared about her health, kept with her agreement.

The model spots that she declared something - an allergy, what she takes - and
the flow asks her to confirm it before anything is written. A fact she got
wrong is removed the same way: confirmed, then removed.
"""
import json
import unittest
from unittest import mock

from app.services import button_router, health_fact_flow, health_facts
from app.services.chat_state import health_fact_drafts
from app.services.structured_response import CHAT_RESPONSE_FORMAT
from app.utils.anonymity import pseudo_id_for

WA_ID = "22890000000"
PSEUDO = pseudo_id_for(WA_ID)


def sent(send):
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
        "request_type": "health_fact",
        "health_fact": "je suis allergique à la pénicilline",
        "health_fact_removed": None,
    }
    base.update(overrides)
    return base


class HealthFactFlowTests(unittest.TestCase):
    def setUp(self):
        health_fact_drafts.clear()
        self.send = mock.Mock()

    def test_she_is_asked_to_confirm_before_anything_is_kept(self):
        with mock.patch.object(health_facts, "record_fact") as record:
            health_fact_flow.start_from_structured(WA_ID, structured(), self.send)

        body, buttons = sent(self.send)[0]
        self.assertIn("pénicilline", body)
        self.assertEqual(
            buttons, [health_fact_flow.CONFIRM_ID, health_fact_flow.REMOVE_ID]
        )
        record.assert_not_called()

    def test_confirming_keeps_the_fact(self):
        with mock.patch.object(health_facts, "record_fact", return_value="f1") as record:
            health_fact_flow.start_from_structured(WA_ID, structured(), self.send)
            button_router.route_button_reply(
                WA_ID, health_fact_flow.CONFIRM_ID, self.send
            )

        record.assert_called_once()
        self.assertEqual(record.call_args.args[1], "je suis allergique à la pénicilline")
        self.assertIn("C'est noté", sent(self.send)[-1][0])

    def test_the_agreement_is_given_with_the_fact(self):
        with mock.patch.object(health_facts, "record_fact", return_value="f1") as record:
            health_fact_flow.start_from_structured(WA_ID, structured(), self.send)
            button_router.route_button_reply(
                WA_ID, health_fact_flow.CONFIRM_ID, self.send
            )

        self.assertEqual(record.call_args.args[0], PSEUDO)

    def test_a_fact_she_wants_forgotten_is_removed(self):
        with mock.patch.object(
            health_facts, "fetch_facts", return_value=["je suis allergique à la pénicilline"]
        ), mock.patch.object(
            health_facts, "fact_id_of", return_value="f1"
        ), mock.patch.object(
            health_facts, "remove_fact", return_value=True
        ) as remove:
            health_fact_flow.start_from_structured(
                WA_ID,
                structured(health_fact="pénicilline", health_fact_removed="pénicilline"),
                self.send,
            )
            button_router.route_button_reply(
                WA_ID, health_fact_flow.REMOVE_ID, self.send
            )

        remove.assert_called_once_with("f1", PSEUDO)
        self.assertIn("oublié", sent(self.send)[-1][0])

    def test_a_failure_to_keep_is_said_and_never_pretended(self):
        with mock.patch.object(health_facts, "record_fact", return_value=None):
            health_fact_flow.start_from_structured(WA_ID, structured(), self.send)
            button_router.route_button_reply(
                WA_ID, health_fact_flow.CONFIRM_ID, self.send
            )

        body = sent(self.send)[-1][0]
        self.assertIn("pas pu le noter", body)
        self.assertNotIn("C'est noté", body)


class NoteTests(unittest.TestCase):
    def test_the_facts_are_given_to_the_model(self):
        note = health_facts.facts_note(["allergique à la pénicilline"])

        self.assertIn("allergique à la pénicilline", note)
        self.assertIn("ses mots", note)

    def test_no_fact_is_no_note(self):
        self.assertIsNone(health_facts.facts_note([]))


class ContractTests(unittest.TestCase):
    def test_the_request_type_is_in_the_schema(self):
        schema = CHAT_RESPONSE_FORMAT["json_schema"]["schema"]
        self.assertIn("health_fact", schema["properties"]["request_type"]["enum"])
        self.assertIn("health_fact", schema["properties"])
        self.assertIn("health_fact_removed", schema["required"])


if __name__ == "__main__":
    unittest.main()
