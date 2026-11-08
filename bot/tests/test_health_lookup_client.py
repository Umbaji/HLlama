import os
import unittest
from unittest.mock import Mock, patch

with patch.dict(os.environ, {"AZURE_OPENAI_API_KEY": "test-only-no-network"}):
    from app.utils.whatsapp_utils import geocode_place, get_nearest


class HealthLookupClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = patch.dict(
            os.environ,
            {
                "NEAREST_API_URL": "https://backend.example",
                "BOT_API_KEY": "health-client-secret",
            },
        )
        self.environment.start()

    def tearDown(self) -> None:
        self.environment.stop()

    @patch("app.utils.whatsapp_utils.requests.get")
    def test_nearest_sends_key_only_as_header(self, get: Mock) -> None:
        response = Mock(status_code=200)
        response.json.return_value = {"status": 200, "error": False, "data": {}}
        get.return_value = response

        get_nearest("pharmacy", 6.2, 1.2, 10)

        request = get.call_args
        self.assertEqual(
            request.kwargs["headers"], {"X-Bot-Api-Key": "health-client-secret"}
        )
        self.assertNotIn("health-client-secret", request.args[0])

    @patch("app.utils.whatsapp_utils.requests.get")
    def test_geocode_sends_key_only_as_header(self, get: Mock) -> None:
        response = Mock(status_code=200)
        response.json.return_value = {
            "data": {"latitude": 6.2, "longitude": 1.2}
        }
        get.return_value = response

        self.assertEqual(geocode_place("Lomé"), response.json.return_value["data"])

        request = get.call_args
        self.assertEqual(
            request.kwargs["headers"], {"X-Bot-Api-Key": "health-client-secret"}
        )
        self.assertNotIn("health-client-secret", request.args[0])

    @patch("app.utils.whatsapp_utils.requests.get")
    def test_provider_response_body_is_not_returned_or_logged(self, get: Mock) -> None:
        response = Mock(status_code=502, text="provider response with private detail")
        get.return_value = response

        result = get_nearest("pharmacy", 6.2, 1.2, 10)

        self.assertEqual(result["status"], 502)
        self.assertNotIn("private detail", str(result))


if __name__ == "__main__":
    unittest.main()
