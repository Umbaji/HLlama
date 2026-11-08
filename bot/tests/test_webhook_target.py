import unittest

from app.services.webhook_target import (
    event_targets_configured_phone,
    extract_target_phone_number_id,
)


def payload_for(phone_number_id: object) -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": phone_number_id},
                        }
                    }
                ]
            }
        ]
    }


class WebhookTargetTests(unittest.TestCase):
    def test_extracts_target_phone_number_id(self) -> None:
        self.assertEqual(
            extract_target_phone_number_id(payload_for("12345")),
            "12345",
        )

    def test_accepts_matching_phone_number(self) -> None:
        self.assertTrue(event_targets_configured_phone(payload_for("12345"), "12345"))

    def test_rejects_another_phone_number(self) -> None:
        self.assertFalse(event_targets_configured_phone(payload_for("99999"), "12345"))

    def test_rejects_target_when_configuration_is_missing(self) -> None:
        self.assertFalse(event_targets_configured_phone(payload_for("12345"), None))

    def test_defers_malformed_payload_to_existing_validation(self) -> None:
        self.assertIsNone(event_targets_configured_phone({"entry": []}, "12345"))
        self.assertIsNone(event_targets_configured_phone(None, "12345"))

    def test_rejects_non_string_target(self) -> None:
        self.assertIsNone(event_targets_configured_phone(payload_for(12345), "12345"))


if __name__ == "__main__":
    unittest.main()
