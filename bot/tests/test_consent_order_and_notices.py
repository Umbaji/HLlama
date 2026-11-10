"""What she sees right after accepting the consent form.

Seen in production: she wrote "Hello", accepted the form, then wrote her real
request. The bot replayed "Hello" (answered in English) before handling the
request.
"""
import json
import unittest
from unittest import mock

from app.services import consent_hold
from app.services.chat_state import held_request
from app.utils.anonymity import pseudo_id_for

WA_ID = "22890000000"
PSEUDO = pseudo_id_for(WA_ID)
CONFIRMATIONS = ("J'ai donne mon consentement ✅",)


def text(body):
    return {"type": "text", "text": {"body": body}}


class SmallTalkIsNotARequest(unittest.TestCase):
    def setUp(self):
        held_request.clear()

    def test_a_greeting_is_not_kept(self):
        for body in ("Hello", "bonjour !", "Salut 🌸", "hi", "Coucou HLlama", "Bonsoir."):
            with self.subTest(body=body):
                self.assertFalse(consent_hold.hold(WA_ID, text(body), CONFIRMATIONS))
        self.assertIsNone(held_request.get(PSEUDO))

    def test_a_real_request_is_still_kept(self):
        self.assertTrue(consent_hold.hold(WA_ID, text("Bonjour, j'ai mal au ventre"), CONFIRMATIONS))

    def test_a_new_request_supersedes_the_kept_one(self):
        self.assertTrue(consent_hold.supersedes(text("Je veux envoyer de l'argent à ma mère"), CONFIRMATIONS))

    def test_what_carries_no_request_lets_the_kept_one_be_replayed(self):
        for message in (
            text("c'est fait"),
            text("C’est fait 👍"),
            text("ok"),
            text(CONFIRMATIONS[0]),
            {"type": "audio"},
            {"type": "interactive"},
        ):
            with self.subTest(message=message):
                self.assertFalse(consent_hold.supersedes(message, CONFIRMATIONS))


class AfterTheForm(unittest.TestCase):
    """The order of what she receives on her first message after accepting."""

    def setUp(self):
        from app.utils import whatsapp_utils

        self.wu = whatsapp_utils
        held_request.clear()
        self.events = []
        self.gate = None
        patches = (
            mock.patch.object(whatsapp_utils, "consent_gate_payload", side_effect=lambda _w: self.gate),
            mock.patch.object(whatsapp_utils, "send_message", side_effect=self._send),
            mock.patch.object(whatsapp_utils, "process_text_message", side_effect=self._handle),
            mock.patch.object(whatsapp_utils, "route_button_reply", return_value=False),
        )
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.counter = 0

    def _send(self, payload):
        payload = json.loads(payload) if isinstance(payload, str) else payload
        self.events.append(("send", payload.get("text", {}).get("body") or payload.get("type")))

    def _handle(self, _wa_id, message):
        self.events.append(("handle", message["text"]["body"]))

    def _receive(self, message):
        self.counter += 1
        message = {"from": WA_ID, "id": f"wamid.order.{self.counter}.{id(self)}", **message}
        self.wu.process_whatsapp_message({"entry": [{"changes": [{"value": {"messages": [message]}}]}]})

    def test_greeting_then_form_then_request(self):
        self.gate = json.dumps({"type": "interactive"})
        self._receive(text("Hello"))
        self.gate = None
        self.events.clear()

        self._receive(text("Je veux envoyer de l'argent à ma mère"))

        self.assertEqual(self.events, [
            ("handle", "Je veux envoyer de l'argent à ma mère"),
        ])

    def test_a_kept_request_is_replayed_after_the_confirmation(self):
        self.gate = json.dumps({"type": "interactive"})
        self._receive(text("J'ai mal au ventre depuis hier"))
        self.gate = None
        self.events.clear()

        self._receive(text("c'est fait"))

        self.assertIn(("handle", "J'ai mal au ventre depuis hier"), self.events)
        self.assertEqual(self.events[-1], ("handle", "c'est fait"))


if __name__ == "__main__":
    unittest.main()
