"""The wording she used, kept without what she said.

The bot can only grow its services from what she really says, so the wordings
it did not understand are recorded. The record holds the shape of a sentence:
no digits, no names, no links, and nothing of what she wrote about her health.
"""
import unittest
from unittest import mock

from app.services import misses


class ScrubTests(unittest.TestCase):
    def test_the_digits_are_removed(self):
        self.assertEqual(
            misses.scrub("traduis le 90000102 pour 5000 francs"),
            "traduis le # pour # francs",
        )

    def test_the_links_and_the_emails_are_removed(self):
        self.assertEqual(
            misses.scrub("envoie le lien https://spamsite.example/x"),
            "envoie le lien",
        )
        self.assertEqual(misses.scrub("ecris a a@b.example"), "ecris a")

    def test_the_name_is_removed(self):
        self.assertEqual(
            misses.scrub("Jean me doit 5000", names=("Jean",)),
            "me doit #",
        )

    def test_the_wording_is_bounded(self):
        self.assertLessEqual(len(misses.scrub("a" * 500)), misses.WORDING_MAX_CHARS)

    def test_an_empty_message_yields_nothing(self):
        self.assertEqual(misses.scrub("   "), "")


class LogTests(unittest.TestCase):
    def test_the_wording_is_sent_scrubbed(self):
        with mock.patch(
            "app.services.misses.post_json", return_value=mock.Mock(status_code=201)
        ) as post:
            misses.log_miss("traduis le 90000102", "translation")

        path, payload = post.call_args.args[0], post.call_args.args[1]
        self.assertEqual(path, "/api/bot/service-misses")
        self.assertEqual(payload["wording"], "traduis le #")
        self.assertEqual(payload["service"], "translation")

    def test_a_failure_is_never_raised(self):
        with mock.patch("app.services.misses.post_json", return_value=None):
            misses.log_miss("traduis", "translation")

    def test_an_empty_wording_is_not_sent(self):
        with mock.patch("app.services.misses.post_json") as post:
            misses.log_miss("   ", "translation")
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
