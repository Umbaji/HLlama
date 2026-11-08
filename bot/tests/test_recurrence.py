"""How often a reminder comes back.

"Every month" is not a number of days: the 31st is missing from four months
of the year, and thirty days lands on another day every time.
"""
import unittest
from datetime import datetime

from app.services import recurrence


class IntervalTests(unittest.TestCase):
    def test_the_backend_repeats_the_patterns_it_can(self):
        self.assertEqual(recurrence.interval_days(recurrence.DAILY), 1)
        self.assertEqual(recurrence.interval_days(recurrence.WEEKLY), 7)

    def test_a_monthly_pattern_is_not_an_interval(self):
        """Thirty days is not a month, and one day is not either."""
        self.assertIsNone(recurrence.interval_days(recurrence.MONTHLY))
        self.assertIsNone(recurrence.interval_days(None))
        self.assertIsNone(recurrence.interval_days("yearly"))


class MonthlyDateTests(unittest.TestCase):
    def test_the_same_day_every_month_at_the_same_hour(self):
        first = datetime(2026, 11, 21, 20, 0)
        dates = recurrence.monthly_dates(first, count=4)
        self.assertEqual(
            [date.strftime("%d/%m %H:%M") for date in dates],
            ["21/11 20:00", "21/12 20:00", "21/01 20:00", "21/02 20:00"],
        )

    def test_the_31st_falls_on_the_last_day_of_the_short_months(self):
        first = datetime(2026, 1, 31, 8, 0)
        dates = recurrence.monthly_dates(first, count=4)
        self.assertEqual(
            [date.strftime("%d/%m") for date in dates],
            ["31/01", "28/02", "31/03", "30/04"],
        )

    def test_a_leap_year_keeps_the_29th_of_february(self):
        first = datetime(2028, 1, 31, 8, 0)
        dates = recurrence.monthly_dates(first, count=3)
        self.assertEqual(dates[1].strftime("%d/%m"), "29/02")

    def test_the_series_is_half_a_year_by_default(self):
        dates = recurrence.monthly_dates(datetime(2026, 11, 21, 20, 0))
        self.assertEqual(len(dates), recurrence.MONTHLY_OCCURRENCES)


class OccurrenceTests(unittest.TestCase):
    def test_a_single_pattern_is_one_reminder(self):
        first = datetime(2026, 11, 21, 20, 0)
        self.assertEqual(recurrence.occurrences(first, recurrence.WEEKLY), [first])

    def test_a_monthly_pattern_is_a_series(self):
        first = datetime(2026, 11, 21, 20, 0)
        self.assertEqual(
            len(recurrence.occurrences(first, recurrence.MONTHLY)),
            recurrence.MONTHLY_OCCURRENCES,
        )


if __name__ == "__main__":
    unittest.main()
