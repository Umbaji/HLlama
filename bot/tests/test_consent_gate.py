import json
import os
import unittest
from unittest import mock

import requests

from app.utils import consent_gate

WA_ID = "22890000000"


class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


def routes(status=None, link=None, status_error=None):
    def fake_post(url, json=None, headers=None, timeout=None):
        if url.endswith("/api/bot/consent/status"):
            if status_error:
                raise status_error
            return status
        if url.endswith("/api/bot/consent/link"):
            return link
        raise AssertionError(url)
    return fake_post


class ConsentGateTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"NEAREST_API_URL": "https://backend.test/", "BOT_API_KEY": "k"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_accepted_lets_the_user_through(self):
        with mock.patch("requests.post", side_effect=routes(FakeResponse(200, {"data": {"status": "accepted"}}))):
            self.assertIsNone(consent_gate.consent_gate_payload(WA_ID))

    def test_phone_is_only_in_the_body(self):
        with mock.patch("requests.post", return_value=FakeResponse(200, {"status": "accepted"})) as post:
            consent_gate.get_consent_status(WA_ID)
        url = post.call_args.args[0]
        self.assertEqual(url, "https://backend.test/api/bot/consent/status")
        self.assertNotIn(WA_ID, url)
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["telnumber"], WA_ID)
        self.assertTrue(body["pseudo_id"])

    def test_pending_gets_the_consent_link(self):
        fake = routes(
            FakeResponse(200, {"data": {"status": "pending"}}),
            FakeResponse(200, {"data": {"url": "https://consent.test/t"}}),
        )
        with mock.patch("requests.post", side_effect=fake):
            payload = json.loads(consent_gate.consent_gate_payload(WA_ID))
        self.assertEqual(payload["interactive"]["action"]["parameters"]["url"], "https://consent.test/t")
        self.assertNotIn("politique", payload["interactive"]["body"]["text"])

    def test_the_prompt_carries_the_policy_link_when_the_backend_sends_it(self):
        fake = routes(
            FakeResponse(200, {"data": {"status": "pending"}}),
            FakeResponse(200, {"data": {"url": "https://consent.test/t", "policy_url": "https://consent.test/policy?lang=fr"}}),
        )
        with mock.patch("requests.post", side_effect=fake):
            payload = json.loads(consent_gate.consent_gate_payload(WA_ID))
        body = payload["interactive"]["body"]["text"]
        self.assertIn("https://consent.test/policy?lang=fr", body)
        self.assertLessEqual(len(body), 1024)
        self.assertEqual(payload["interactive"]["action"]["parameters"]["url"], "https://consent.test/t")

    def test_backend_down_fails_closed(self):
        with mock.patch("requests.post", side_effect=routes(status_error=requests.ConnectionError("down"))):
            payload = json.loads(consent_gate.consent_gate_payload(WA_ID))
        self.assertEqual(payload["text"]["body"], consent_gate.SERVICE_UNAVAILABLE_TEXT)

    def test_server_error_and_garbage_fail_closed(self):
        for response in (FakeResponse(500, {}), FakeResponse(200, None), FakeResponse(200, {"data": {"status": "maybe"}})):
            with self.subTest(status=response.status_code), \
                    mock.patch("requests.post", side_effect=routes(response)):
                self.assertIsNotNone(consent_gate.consent_gate_payload(WA_ID))
                self.assertFalse(consent_gate.has_consented(WA_ID))

    def test_missing_backend_url_fails_closed(self):
        with mock.patch.dict(os.environ, {"NEAREST_API_URL": "", "HLLAMA_BACKEND_URL": ""}), \
                mock.patch("requests.post") as post:
            self.assertFalse(consent_gate.has_consented(WA_ID))
        post.assert_not_called()

    def test_link_failure_falls_back_to_unavailable(self):
        fake = routes(FakeResponse(200, {"status": "refused"}), FakeResponse(503, {}))
        with mock.patch("requests.post", side_effect=fake):
            payload = json.loads(consent_gate.consent_gate_payload(WA_ID))
        self.assertEqual(payload["type"], "text")

    def test_legacy_backend_url_alias(self):
        with mock.patch.dict(os.environ, {"NEAREST_API_URL": "", "HLLAMA_BACKEND_URL": "https://legacy.test"}), \
                mock.patch("requests.post", return_value=FakeResponse(200, {"status": "accepted"})) as post:
            self.assertTrue(consent_gate.has_consented(WA_ID))
        self.assertTrue(post.call_args.args[0].startswith("https://legacy.test/api/"))


if __name__ == "__main__":
    unittest.main()
