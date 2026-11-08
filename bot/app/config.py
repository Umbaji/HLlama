import sys
import os
from dotenv import load_dotenv
import logging


_PSEUDO_ID_PLACEHOLDERS = {"change-me-pseudo-id-secret", "your_pseudo_id_secret"}


def require_pseudo_id_secret(value: str | None) -> str:
    if value is None or not value.strip():
        raise ValueError(
            "Invalid configuration: PSEUDO_ID_SECRET must be configured."
        )
    if value.strip().lower() in _PSEUDO_ID_PLACEHOLDERS:
        raise ValueError(
            "Invalid configuration: PSEUDO_ID_SECRET must be configured."
        )
    return value


def load_configurations(app):
    load_dotenv()
    app.config["PSEUDO_ID_SECRET"] = require_pseudo_id_secret(
        os.getenv("PSEUDO_ID_SECRET")
    )
    app.config["ACCESS_TOKEN"] = os.getenv("ACCESS_TOKEN")
    app.config["YOUR_PHONE_NUMBER"] = os.getenv("YOUR_PHONE_NUMBER")
    app.config["APP_ID"] = os.getenv("APP_ID")
    app.config["APP_SECRET"] = os.getenv("APP_SECRET")
    app.config["RECIPIENT_WAID"] = os.getenv("RECIPIENT_WAID")
    app.config["VERSION"] = os.getenv("VERSION")
    app.config["PHONE_NUMBER_ID"] = os.getenv("PHONE_NUMBER_ID")
    app.config["VERIFY_TOKEN"] = os.getenv("VERIFY_TOKEN")


def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )
