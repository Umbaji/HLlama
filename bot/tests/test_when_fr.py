"""The French date and time she types, read without a clock of its own."""
import unittest
from datetime import datetime

from app.services.when_fr import parse_when

# A Tuesday, so "lundi" is six days ahead and "mardi" a full week.
NOW = datetime(2026, 10, 20, 10, 30)


class ParseWhenTest(unittest.TestCase):
    def test_iso_value_from_the_model(self):
        self.assertEqual(parse_when("2026-10-25T08:00:00", NOW), datetime(2026, 10, 25, 8, 0))

    def test_iso_with_a_space_and_a_trailing_zone(self):
        self.assertEqual(parse_when("2026-10-25 08:00", NOW), datetime(2026, 10, 25, 8, 0))
        self.assertEqual(parse_when("2026-10-25T08:00:00Z", NOW), datetime(2026, 10, 25, 8, 0))

    def test_day_and_month_default_to_eight_in_the_morning(self):
        self.assertEqual(parse_when("25/10", NOW), datetime(2026, 10, 25, 8, 0))
        self.assertEqual(parse_when("le 25-10 a 18h", NOW), datetime(2026, 10, 25, 18, 0))

    def test_day_month_year(self):
        self.assertEqual(parse_when("03/01/2027 a 7h30", NOW), datetime(2027, 1, 3, 7, 30))
        self.assertEqual(parse_when("03/01/27", NOW), datetime(2027, 1, 3, 8, 0))

    def test_a_day_month_already_past_rolls_to_next_year(self):
        self.assertEqual(parse_when("5/3", NOW), datetime(2027, 3, 5, 8, 0))

    def test_tomorrow_and_the_day_after(self):
        self.assertEqual(parse_when("demain à 20h", NOW), datetime(2026, 10, 21, 20, 0))
        self.assertEqual(parse_when("après-demain", NOW), datetime(2026, 10, 22, 8, 0))

    def test_today_keeps_the_day_when_the_hour_is_still_ahead(self):
        self.assertEqual(parse_when("aujourd'hui à 18h", NOW), datetime(2026, 10, 20, 18, 0))

    def test_today_at_an_hour_already_gone_is_refused(self):
        self.assertIsNone(parse_when("aujourd'hui à 8h", NOW))

    def test_in_n_units(self):
        self.assertEqual(parse_when("dans 3 jours", NOW), datetime(2026, 10, 23, 10, 30))
        self.assertEqual(parse_when("dans 2 semaines", NOW), datetime(2026, 11, 3, 10, 30))
        self.assertEqual(parse_when("dans 5 heures", NOW), datetime(2026, 10, 20, 15, 30))
        self.assertEqual(parse_when("dans 1 mois", NOW), datetime(2026, 11, 19, 10, 30))

    def test_a_weekday_is_the_next_one(self):
        self.assertEqual(parse_when("lundi à 7h", NOW), datetime(2026, 10, 26, 7, 0))
        self.assertEqual(parse_when("mardi", NOW), datetime(2026, 10, 27, 8, 0))

    def test_weekday_prochain_skips_this_week(self):
        self.assertEqual(parse_when("lundi prochain", NOW), datetime(2026, 11, 2, 8, 0))

    def test_a_bare_hour_is_today_then_tomorrow(self):
        self.assertEqual(parse_when("20h", NOW), datetime(2026, 10, 20, 20, 0))
        self.assertEqual(parse_when("20h30", NOW), datetime(2026, 10, 20, 20, 30))
        self.assertEqual(parse_when("8h", NOW), datetime(2026, 10, 21, 8, 0))
        self.assertEqual(parse_when("8:30", NOW), datetime(2026, 10, 21, 8, 30))

    def test_a_delay_in_seconds_becomes_the_next_minute(self):
        """"dans 10s" cannot be honoured: the poller runs every 30 seconds."""
        self.assertEqual(parse_when("dans 10s", NOW), datetime(2026, 10, 20, 10, 31))
        self.assertEqual(parse_when("Dans 2s", NOW), datetime(2026, 10, 20, 10, 31))
        self.assertEqual(parse_when("A 2s", NOW), datetime(2026, 10, 20, 10, 31))

    def test_abbreviated_and_spelled_out_delays(self):
        self.assertEqual(parse_when("dans 2 min", NOW), datetime(2026, 10, 20, 10, 32))
        self.assertEqual(parse_when("a 10 min", NOW), datetime(2026, 10, 20, 10, 40))
        self.assertEqual(parse_when("dans une minute", NOW), datetime(2026, 10, 20, 10, 31))
        self.assertEqual(parse_when("dans deux semaines", NOW), datetime(2026, 11, 3, 10, 30))
        self.assertEqual(parse_when("dans 20 h", NOW), datetime(2026, 10, 21, 6, 30))

    def test_an_hour_said_with_a_is_not_a_delay(self):
        """"demain a 20h" is eight in the evening, not twenty hours from now."""
        self.assertEqual(parse_when("demain à 20h", NOW), datetime(2026, 10, 21, 20, 0))
        self.assertEqual(parse_when("a 8h", NOW), datetime(2026, 10, 21, 8, 0))

    def test_seconds_are_dropped(self):
        self.assertEqual(parse_when("2026-10-25T08:00:59", NOW).second, 0)

    def test_a_date_already_gone_is_refused(self):
        self.assertIsNone(parse_when("2026-10-19T08:00:00", NOW))
        self.assertIsNone(parse_when("2020-01-01", NOW))

    def test_an_impossible_date_is_refused(self):
        self.assertIsNone(parse_when("32/13", NOW))
        self.assertIsNone(parse_when("25h", NOW))

    def test_no_date_at_all(self):
        for text in ("", "   ", None, "quand tu veux", "n/a"):
            self.assertIsNone(parse_when(text, NOW), text)


if __name__ == "__main__":
    unittest.main()
