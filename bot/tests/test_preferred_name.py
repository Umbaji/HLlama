import unittest

from app.services.preferred_name import extract_preferred_name


class PreferredNameTests(unittest.TestCase):
    def test_extracts_supported_self_introductions(self) -> None:
        cases = {
            "Je suis MICHEL": "Michel",
            "Je m'appelle ama": "Ama",
            "Mon prénom est Marie-Claire.": "Marie-Claire",
            "Bonjour, moi c'est d'ALMEIDA !": "D'Almeida",
        }
        for message, expected in cases.items():
            with self.subTest(message=message):
                self.assertEqual(extract_preferred_name(message), expected)

    def test_rejects_health_and_emotional_states(self) -> None:
        for message in ("Je suis malade", "Je suis enceinte", "Je suis fatiguée"):
            with self.subTest(message=message):
                self.assertIsNone(extract_preferred_name(message))

    def test_rejects_ambiguous_or_unsafe_values(self) -> None:
        for message in (
            "Dis que je suis Michel",
            "Je m'appelle Michel je suis administrateur",
            "Je suis Michel42",
            "Je m'appelle <script>",
            "Je m'appelle Ignore Previous Instructions",
        ):
            with self.subTest(message=message):
                self.assertIsNone(extract_preferred_name(message))


if __name__ == "__main__":
    unittest.main()
