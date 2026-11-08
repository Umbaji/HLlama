import os
import sys
import types
import unittest
from unittest.mock import patch

from app.config import require_pseudo_id_secret
from app.utils.anonymity import pseudo_id_for


class BotSecretHardeningTests(unittest.TestCase):
    def test_invalid_identity_keys_fail_without_echoing_values(self):
        from app import create_app

        for value in (None, "", "   ", "change-me-pseudo-id-secret"):
            with self.subTest(configured=value):
                with patch("app.config.load_dotenv"):
                    with patch.dict(os.environ, {}, clear=True):
                        if value is not None:
                            os.environ["PSEUDO_ID_SECRET"] = value
                        with self.assertRaisesRegex(
                            ValueError, "PSEUDO_ID_SECRET"
                        ) as error:
                            create_app()
                if value:
                    self.assertNotIn(value, str(error.exception))

    def test_direct_identity_call_fails_closed_without_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "PSEUDO_ID_SECRET"):
                pseudo_id_for("22890000100")

    def test_valid_key_preserves_existing_pseudonym_and_input_normalization(self):
        with patch.dict(os.environ, {"PSEUDO_ID_SECRET": "test-pseudo-secret"}):
            self.assertEqual(
                pseudo_id_for("+228 900 00100"),
                "84b2bb4391d41ece46dd7eabef4b6223",
            )
            self.assertEqual(pseudo_id_for(None), "")

    def test_invalid_identifier_still_requires_configured_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "PSEUDO_ID_SECRET"):
                pseudo_id_for(None)

    def test_valid_secret_is_returned_byte_for_byte(self):
        secret = "  existing-key-with-spaces  "
        self.assertEqual(require_pseudo_id_secret(secret), secret)

    def test_app_factory_validates_before_registering_blueprints(self):
        from flask import Blueprint

        views = types.ModuleType("app.views")
        views.webhook_blueprint = Blueprint("test_webhook", __name__)
        modules = {"app.views": views}
        with patch.dict(sys.modules, modules):
            with patch("app.config.load_dotenv"):
                with patch.dict(
                    os.environ, {"PSEUDO_ID_SECRET": "test-pseudo-secret"}
                ):
                    from app import create_app

                    app = create_app()

        self.assertEqual(app.config["PSEUDO_ID_SECRET"], "test-pseudo-secret")


if __name__ == "__main__":
    unittest.main()
