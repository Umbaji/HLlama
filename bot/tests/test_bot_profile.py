import os
import unittest
from unittest.mock import Mock, patch

from app.services.bot_profile import fetch_preferred_name, resolve_preferred_name


class BotProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = patch.dict(
            os.environ,
            {
                "NEAREST_API_URL": "https://backend.example",
                "BOT_API_KEY": "bot-secret",
                "PSEUDO_ID_SECRET": "pseudo-secret",
            },
        )
        self.environment.start()

    def tearDown(self) -> None:
        self.environment.stop()

    @staticmethod
    def _response(name: str | None) -> Mock:
        response = Mock(status_code=200)
        response.json.return_value = {
            "status": 200,
            "error": False,
            "data": {"preferred_name": name},
        }
        return response

    @patch("app.services.bot_profile.requests.get")
    def test_profile_reads_are_not_cached(self, get: Mock) -> None:
        get.side_effect = [self._response("Michel"), self._response("Ama")]

        self.assertEqual(fetch_preferred_name("22890000100"), "Michel")
        self.assertEqual(fetch_preferred_name("22890000100"), "Ama")

        self.assertEqual(get.call_count, 2)
        self.assertNotIn("22890000100", get.call_args.args[0])

    @patch("app.services.bot_profile.requests.get")
    @patch("app.services.bot_profile.requests.put")
    def test_explicit_name_is_persisted_before_use(self, put: Mock, get: Mock) -> None:
        put.return_value = self._response("Michel")

        name = resolve_preferred_name("22890000100", "Je suis MICHEL")

        self.assertEqual(name, "Michel")
        get.assert_not_called()
        self.assertEqual(put.call_args.kwargs["json"]["preferred_name"], "Michel")


if __name__ == "__main__":
    unittest.main()
