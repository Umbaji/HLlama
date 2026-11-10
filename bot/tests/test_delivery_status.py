import hashlib
import hmac
import importlib
import json
import sys
import types
import unittest
from unittest import mock

from app.services import delivery_status


def status_event(*statuses):
    return {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {
            "metadata": {"phone_number_id": "PNID"},
            "statuses": list(statuses),
        }}]}],
    }


FAILED = {
    "id": "wamid.FAIL",
    "status": "failed",
    "recipient_id": "22890000000",
    "errors": [{
        "code": 131047,
        "title": "Re-engagement message",
        "message": "More than 24 hours have passed since the recipient last replied",
        "error_data": {"details": "recipient 22890000000"},
    }],
}
DELIVERED = {"id": "wamid.OK", "status": "delivered", "recipient_id": "22890000000"}


class DeliveryStatusTests(unittest.TestCase):
    def test_only_failed_statuses_are_reported_without_pii(self):
        reports = delivery_status.failed_deliveries(status_event(DELIVERED, FAILED))
        self.assertEqual(reports, [{
            "wa_message_id": "wamid.FAIL",
            "error_code": 131047,
            "error_title": "Re-engagement message",
        }])
        self.assertNotIn("22890000000", json.dumps(reports))

    def test_failures_are_logged_without_pii(self):
        with self.assertLogs(level="WARNING") as logs:
            self.assertEqual(delivery_status.log_delivery_failures(status_event(FAILED)), 1)
        self.assertIn("131047", "\n".join(logs.output))
        self.assertNotIn("22890000000", "\n".join(logs.output))

    def test_malformed_bodies_are_harmless(self):
        for body in (None, {}, {"entry": [{}]}, {"entry": [{"changes": [{"value": {"statuses": [{"status": "failed"}]}}]}]}):
            with self.subTest(body=body):
                self.assertEqual(delivery_status.failed_deliveries(body), [])


class StatusWebhookTests(unittest.TestCase):
    """Drives the real /webhook route with the heavy speech module stubbed."""

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
        self.app.config.update(APP_SECRET="secret", PHONE_NUMBER_ID="PNID")
        self.app.register_blueprint(views.webhook_blueprint)
        self.client = self.app.test_client()

    def post(self, body):
        raw = json.dumps(body)
        signature = hmac.new(b"secret", raw.encode(), hashlib.sha256).hexdigest()
        return self.client.post(
            "/webhook",
            data=raw,
            content_type="application/json",
            headers={"X-Hub-Signature-256": f"sha256={signature}"},
        )

    def test_failed_status_is_logged_and_acknowledged(self):
        with self.assertLogs(level="WARNING") as logs:
            response = self.post(status_event(FAILED))
        self.assertEqual(response.status_code, 200)
        self.assertIn("WhatsApp delivery failed", "\n".join(logs.output))

    def test_other_statuses_are_acknowledged_silently(self):
        with mock.patch.object(delivery_status.logging, "warning") as warning:
            response = self.post(status_event(DELIVERED))
        self.assertEqual(response.status_code, 200)
        warning.assert_not_called()


if __name__ == "__main__":
    unittest.main()
