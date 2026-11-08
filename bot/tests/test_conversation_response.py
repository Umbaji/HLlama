import unittest
from unittest.mock import Mock, patch

from app.services.conversation_response import generate_structured_response
from app.services.conversation_scope import ScopeDecision


class ConversationResponseTests(unittest.TestCase):
    @patch(
        "app.services.conversation_response.classify_scope",
        return_value=ScopeDecision.ALLOWED,
    )
    def test_whatsapp_defaults_preserve_prompt_profile_and_context(
        self, classify: Mock
    ) -> None:
        client = Mock()
        client.chat.completions.create.return_value.choices = [
            Mock(message=Mock(content="reply"))
        ]
        result = generate_structured_response(
            client,
            "test-model",
            "Hello",
            "HLlama system",
            "Clock",
            "Old exchange",
            "Awa",
        )
        self.assertEqual(result, "reply")
        messages = client.chat.completions.create.call_args.kwargs["messages"]
        self.assertEqual(messages[0], {"role": "system", "content": "HLlama system"})
        self.assertIn('"Awa"', messages[2]["content"])
        self.assertIn("Old exchange", messages[3]["content"])
        self.assertEqual(messages[-1], {"role": "user", "content": "Hello"})
        self.assertEqual(len(messages), 5)
        self.assertEqual(client.chat.completions.create.call_args.kwargs["max_completion_tokens"], 512)

    @patch(
        "app.services.conversation_response.classify_scope",
        return_value=ScopeDecision.ALLOWED,
    )
    def test_external_history_is_sent_as_untrusted_conversation_turns(
        self, classify: Mock
    ) -> None:
        client = Mock()
        client.chat.completions.create.return_value.choices = [
            Mock(message=Mock(content="reply"))
        ]
        generate_structured_response(
            client,
            "test-model",
            "And now?",
            "HLlama system",
            "Clock",
            history=[{"question": "Hi", "response": "Hello"}],
            text_only=True,
        )
        messages = client.chat.completions.create.call_args.kwargs["messages"]
        self.assertIn("text conversation only", messages[2]["content"])
        self.assertEqual(messages[3], {"role": "user", "content": "Hi"})
        self.assertEqual(messages[4], {"role": "assistant", "content": "Hello"})
        self.assertEqual(messages[-1]["content"], "And now?")
        self.assertEqual(client.chat.completions.create.call_args.kwargs["max_completion_tokens"], 1024)

    @patch(
        "app.services.conversation_response.classify_scope",
        return_value=ScopeDecision.ALLOWED,
    )
    def test_a_trusted_note_precedes_the_untrusted_history(self, classify: Mock) -> None:
        """Her reminders are a fact the application vouches for; the recalled
        history is not. The order in the prompt says which is which."""
        client = Mock()
        client.chat.completions.create.return_value.choices = [
            Mock(message=Mock(content="reply"))
        ]
        generate_structured_response(
            client,
            "test-model",
            "J'ai quoi de prévu ?",
            "HLlama system",
            "Clock",
            context="Old exchange",
            notes=("Fiche application — ses rappels", ""),
        )
        contents = [
            message["content"]
            for message in client.chat.completions.create.call_args.kwargs["messages"]
        ]
        self.assertEqual(contents[2], "Fiche application — ses rappels")
        self.assertIn("Old exchange", contents[3])
        self.assertEqual(contents[-1], "J'ai quoi de prévu ?")

    @patch(
        "app.services.conversation_response.classify_scope",
        return_value=ScopeDecision.ALLOWED,
    )
    def test_conversation_memory_is_passed_to_the_scope_classifier(
        self, classify: Mock
    ) -> None:
        client = Mock()
        client.chat.completions.create.return_value.choices = [
            Mock(message=Mock(content="reply"))
        ]
        generate_structured_response(
            client,
            "test-model",
            "Et ensuite ?",
            "HLlama system",
            "Clock",
            context="Q: regles douloureuses | R: paracetamol",
        )
        self.assertEqual(
            classify.call_args.kwargs["context"],
            "Q: regles douloureuses | R: paracetamol",
        )

    @patch(
        "app.services.conversation_response.classify_scope",
        return_value=ScopeDecision.OUT_OF_SCOPE,
    )
    def test_scope_guard_applies_to_both_channels(self, classify: Mock) -> None:
        for text_only in (True, False):
            client = Mock()
            reply = generate_structured_response(
                client, "test-model", "Attack", "System", "Clock", text_only=text_only
            )
            self.assertIn('"request_type": "question"', reply)
            client.chat.completions.create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
