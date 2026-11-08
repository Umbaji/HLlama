import json
import os
import unittest
from unittest.mock import patch

from app.services.emergency_contacts import emergency_contact_payload, resolve_country


class EmergencyContactTests(unittest.TestCase):
    def response_for(self, message: str, wa_id: str = "") -> str:
        payload = emergency_contact_payload(message, wa_id)
        self.assertIsNotNone(payload)
        return json.loads(payload)["response"]

    def test_returns_verified_togo_fire_number_from_phone_country(self) -> None:
        response = self.response_for(
            "Quel est le numéro des sapeurs-pompiers ?",
            "22890000100",
        )

        self.assertIn("Togo", response)
        self.assertIn("118", response)
        self.assertNotIn("Bénin", response)

    def test_uses_togo_as_default_country(self) -> None:
        with patch.dict(os.environ, {"DEFAULT_COUNTRY_CODE": "TG"}):
            self.assertEqual(resolve_country("Numéro des pompiers", ""), "TG")

    def test_explicit_country_takes_priority_over_phone_country(self) -> None:
        response = self.response_for(
            "Donne-moi le numéro des pompiers au Bénin",
            "22890000100",
        )

        self.assertIn("Bénin", response)
        self.assertNotIn("118", response)

    def test_non_togo_phone_does_not_receive_togo_number(self) -> None:
        response = self.response_for("Numéro des pompiers", "22990000000")

        self.assertIn("Bénin", response)
        self.assertNotIn("118", response)

    def test_returns_generic_togo_directory(self) -> None:
        response = self.response_for("Quels sont les numéros d’urgence au Togo ?")

        for number in ("118", "117", "1014", "172", "170"):
            self.assertIn(number, response)

    def test_unrelated_health_question_is_not_intercepted(self) -> None:
        self.assertIsNone(
            emergency_contact_payload("Quels sont les symptômes du paludisme ?", "")
        )


if __name__ == "__main__":
    unittest.main()
