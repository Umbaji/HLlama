import hmac
import importlib
import sys
import types
import unittest
from unittest import mock


class WebhookVerificationTests(unittest.TestCase):
    def setUp(self):
        stub = types.ModuleType("app.utils.whatsapp_utils")
        stub.process_whatsapp_message = mock.Mock()
        stub.is_valid_whatsapp_message = mock.Mock(return_value=False)
        modules = mock.patch.dict(sys.modules, {"app.utils.whatsapp_utils": stub})
        modules.start()
        self.addCleanup(modules.stop)
        sys.modules.pop("app.views", None)
        self.addCleanup(sys.modules.pop, "app.views", None)
        views = importlib.import_module("app.views")

        from flask import Flask

        self.app = Flask(__name__)
        self.app.config["VERIFY_TOKEN"] = "configured-token"
        self.app.register_blueprint(views.webhook_blueprint)
        self.client = self.app.test_client()

    def test_matching_token_returns_challenge_using_constant_time_compare(self):
        with mock.patch(
            "app.views.hmac.compare_digest", wraps=hmac.compare_digest
        ) as compare:
            response = self.client.get(
                "/webhook?hub.mode=subscribe&hub.verify_token=configured-token"
                "&hub.challenge=challenge"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(as_text=True), "challenge")
        compare.assert_called_once_with("configured-token", "configured-token")

    def test_wrong_token_and_mode_are_forbidden(self):
        with mock.patch(
            "app.views.hmac.compare_digest", wraps=hmac.compare_digest
        ) as compare:
            response = self.client.get(
                "/webhook?hub.mode=subscribe&hub.verify_token=wrong-token"
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["message"], "Verification failed")
        compare.assert_called_once_with("wrong-token", "configured-token")

        response = self.client.get(
            "/webhook?hub.mode=unsubscribe&hub.verify_token=configured-token"
        )
        self.assertEqual(response.status_code, 403)

    def test_missing_configured_token_fails_closed(self):
        self.app.config["VERIFY_TOKEN"] = None

        response = self.client.get(
            "/webhook?hub.mode=subscribe&hub.verify_token=configured-token"
        )

        self.assertEqual(response.status_code, 403)

    def test_missing_parameters_keep_existing_bad_request_contract(self):
        response = self.client.get("/webhook?hub.mode=subscribe")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["message"], "Missing parameters")


if __name__ == "__main__":
    unittest.main()
