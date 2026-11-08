import unittest
from unittest.mock import patch

from config import settings
from helpers.timezones import iana_zone_for_telnumber


class TimezoneResolutionTests(unittest.TestCase):
    def test_togo_number_resolves_to_lome(self) -> None:
        self.assertEqual(iana_zone_for_telnumber("+22890000100"), "Africa/Lome")

    def test_invalid_number_uses_configured_togo_fallback(self) -> None:
        with patch.object(settings, "DEFAULT_REMINDER_TIMEZONE", "Africa/Lome"):
            self.assertEqual(iana_zone_for_telnumber("invalid"), "Africa/Lome")

    def test_benin_number_keeps_its_phone_derived_timezone(self) -> None:
        self.assertEqual(
            iana_zone_for_telnumber("+2290197000000"),
            "Africa/Porto-Novo",
        )


if __name__ == "__main__":
    unittest.main()
