import os
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch

from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    RateLimitError,
)

from app.services.model_failure import category_for_provider_error


class ProviderFailureCategoryTests(unittest.TestCase):
    def setUp(self) -> None:
        request = SimpleNamespace(method="POST", url="https://example.test/chat")
        self.rate_limit = RateLimitError(
            "limited",
            response=SimpleNamespace(
                status_code=429,
                request=request,
                headers={"x-request-id": "test"},
            ),
            body=None,
        )
        self.authentication = AuthenticationError(
            "unauthorized",
            response=SimpleNamespace(
                status_code=401,
                request=request,
                headers={"x-request-id": "test"},
            ),
            body=None,
        )
        self.timeout = APITimeoutError(request=request)
        self.connection = APIConnectionError(message="unavailable", request=request)

    def test_provider_errors_map_to_safe_categories(self) -> None:
        cases = (
            (self.rate_limit, "rate_limited"),
            (self.timeout, "timeout"),
            (self.authentication, "authentication"),
            (self.connection, "provider_error"),
            (RuntimeError("private detail"), "provider_error"),
        )
        for error, expected in cases:
            with self.subTest(category=expected):
                self.assertEqual(category_for_provider_error(error), expected)


class GenerationFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        with patch.dict(os.environ, {"AZURE_OPENAI_API_KEY": "unit-test-key"}):
            from app.utils import whatsapp_utils

        self.whatsapp_utils = whatsapp_utils

    def _patch_neutral_routes(self, stack: ExitStack) -> None:
        neutral: dict[str, bool | None | str] = {
            "awaiting_her_answer": False,
            "intents.detect": None,
            "menu.act_on_intent": False,
            "reminder_flow.consume_text": False,
            "emergency_offer.pop": False,
            "reminder_update.consume_text": False,
            "is_detail_request": False,
            "extract_cancel_number": None,
            "is_reminder_optout": False,
            "is_list_request": False,
            "consume_feedback_comment": False,
            "is_maps_link": False,
            "resolve_preferred_name": None,
            "build_context_memory": "",
        }
        for name, value in neutral.items():
            stack.enter_context(
                patch(f"app.utils.whatsapp_utils.{name}", return_value=value)
            )
        stack.enter_context(
            patch("app.utils.whatsapp_utils.menu.number_in", return_value=None)
        )
        stack.enter_context(patch("app.utils.whatsapp_utils.handle_request"))

    def process_with(
        self,
        generated_result: str | None = None,
        generated_error: Exception | None = None,
    ) -> tuple[str | None, Mock, Mock]:
        with ExitStack() as stack:
            self._patch_neutral_routes(stack)
            send = stack.enter_context(patch("app.utils.whatsapp_utils.send_message"))
            persist = stack.enter_context(
                patch("app.utils.whatsapp_utils.push_exchange_to_backend")
            )
            generation = patch("app.utils.whatsapp_utils.generate_response")
            if generated_error is not None:
                stack.enter_context(generation).side_effect = generated_error
            else:
                stack.enter_context(generation).return_value = generated_result
            result = self.whatsapp_utils.process_text_message(
                "+22890000000", {"text": {"body": "private question"}}
            )
        return result, send, persist

    def test_provider_failure_sends_fallback_without_persisting_it(self) -> None:
        rate_error = RateLimitError(
            "sensitive provider body",
            response=SimpleNamespace(
                status_code=429,
                request=SimpleNamespace(method="POST", url="https://example.test/chat"),
                headers={"x-request-id": "test"},
            ),
            body=None,
        )
        with self.assertLogs(level="ERROR") as captured:
            result, send, persist = self.process_with(generated_error=rate_error)

        self.assertEqual(result, self.whatsapp_utils.GENERATION_FALLBACK_MESSAGE)
        send.assert_called_once()
        persist.assert_not_called()
        self.assertIn("category=rate_limited", captured.output[0])
        self.assertNotIn("sensitive provider body", " ".join(captured.output))
        self.assertNotIn("private question", " ".join(captured.output))

    def test_invalid_structured_output_sends_fallback_without_persisting_it(self) -> None:
        with self.assertLogs(level="WARNING") as captured:
            result, send, persist = self.process_with(generated_result="not-json")

        self.assertEqual(result, self.whatsapp_utils.GENERATION_FALLBACK_MESSAGE)
        send.assert_called_once()
        persist.assert_not_called()
        self.assertIn("category=invalid_response", captured.output[0])

    def test_valid_answer_is_still_persisted(self) -> None:
        result, _, persist = self.process_with(
            generated_result='{"request_type":"question","response":"Réponse"}'
        )

        self.assertEqual(result, "Réponse")
        persist.assert_called_once_with(
            "+22890000000",
            "private question",
            response="Réponse",
            request_type="question",
        )


if __name__ == "__main__":
    unittest.main()
