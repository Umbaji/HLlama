"""The question asked instead of a change of subject.

The bot answered anything it did not understand with "let us talk about your
health". A request that is almost understood deserves a question she can
answer in one word.
"""
import unittest

from app.services import clarification
from app.services.conversation_scope import OUT_OF_SCOPE_RESPONSE, out_of_scope_payload


class ClarificationTests(unittest.TestCase):
    def test_a_reminder_request_gets_a_question(self):
        question = clarification.clarification("programme moi un rappel pour demain")

        self.assertIsNotNone(question)
        self.assertIn("rappel", question.lower())

    def test_the_accents_do_not_matter(self):
        self.assertIsNotNone(clarification.clarification("décale mon rappel de jeudi"))
        self.assertIsNotNone(clarification.clarification("decale mon rappel de jeudi"))

    def test_a_health_question_is_left_to_the_model(self):
        """The health redirection is right for a health question."""
        self.assertIsNone(clarification.clarification("j'ai mal au ventre"))
        self.assertIsNone(clarification.clarification("comment appelle-t-on la pilule du lendemain"))

    def test_an_unrelated_subject_is_left_to_the_model(self):
        self.assertIsNone(clarification.clarification("ecris moi un poeme"))
        self.assertIsNone(clarification.clarification("qui a gagne le match hier"))

    def test_the_service_is_recognised(self):
        self.assertEqual(clarification.service_of("annule mon rappel"), "cancel")
        self.assertEqual(clarification.service_of("decale mon rappel"), "move")
        self.assertEqual(clarification.service_of("programme un rappel"), "reminder")
        self.assertIsNone(clarification.service_of("bonjour"))


class OutOfScopePayloadTests(unittest.TestCase):
    def _response(self, message: str) -> str:
        import json

        return json.loads(out_of_scope_payload(message))["response"]

    def test_a_service_request_is_asked_about(self):
        response = self._response("programme moi un rappel pour demain")

        self.assertNotEqual(response, OUT_OF_SCOPE_RESPONSE)
        self.assertIn("rappel", response.lower())

    def test_an_unrelated_subject_still_gets_the_redirection(self):
        response = self._response("ecris moi un poeme")

        self.assertEqual(response, OUT_OF_SCOPE_RESPONSE)

    def test_the_payload_carries_every_field_of_the_contract(self):
        import json

        payload = json.loads(out_of_scope_payload("bonjour"))

        self.assertEqual(
            set(payload),
            {
                "request_type", "target_language", "target_format", "request_content",
                "scheduled_at", "reminder_kind", "repeat_interval_days",
                "reminder_number", "response",
            },
        )


if __name__ == "__main__":
    unittest.main()
