"""The consent page: rendering, language, headers and the bot handshake.

The consent API itself is covered by test_consent.py and is untouched here.
"""
import json
import re
from datetime import datetime, timezone
from html import escape
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.consent import router
from services.consent_page import (
    DEFAULT_LANGUAGE,
    render_consent_page,
    resolve_language,
)


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_page_renders_in_french_by_default(client: TestClient) -> None:
    response = client.get("/consent")

    assert response.status_code == 200
    assert response.headers["content-language"] == "fr"
    assert 'lang="fr"' in response.text
    assert "Avant de commencer" in response.text


def test_page_renders_in_english_on_request(client: TestClient) -> None:
    response = client.get("/consent", params={"lang": "en"})

    assert response.headers["content-language"] == "en"
    assert 'lang="en"' in response.text
    assert "Before you start" in response.text


def test_unknown_language_falls_back_to_french(client: TestClient) -> None:
    response = client.get("/consent", params={"lang": "zz"})

    assert response.headers["content-language"] == "fr"


def test_accept_language_header_is_honoured(client: TestClient) -> None:
    response = client.get("/consent", headers={"Accept-Language": "en-GB,en;q=0.9"})

    assert response.headers["content-language"] == "en"


@pytest.mark.parametrize(
    ("requested", "header", "expected"),
    [
        ("en", None, "en"),
        ("FR", "en", "fr"),
        (None, "en-US,en;q=0.8", "en"),
        (None, "de,es;q=0.7", DEFAULT_LANGUAGE),
        (None, None, DEFAULT_LANGUAGE),
        ("", "", DEFAULT_LANGUAGE),
    ],
)
def test_language_negotiation(requested: str | None, header: str | None, expected: str) -> None:
    assert resolve_language(requested, header) == expected


def test_security_headers_are_set(client: TestClient) -> None:
    headers = client.get("/consent").headers

    assert "default-src 'none'" in headers["content-security-policy"]
    assert "script-src 'self'" in headers["content-security-policy"]
    assert "'unsafe-inline'" not in headers["content-security-policy"]
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["cache-control"] == "no-store"
    assert headers["x-content-type-options"] == "nosniff"


def test_no_inline_style_or_executable_script() -> None:
    """The CSP above only holds if nothing executable is inlined in the page."""
    html = render_consent_page("fr").html

    assert "<style" not in html
    assert not re.search(r"<script(?![^>]*\bsrc=)(?![^>]*application/json)", html)
    assert 'href="/static/consent/consent.css"' in html
    for script in ("consent-core.js", "consent.js", "consent-reading.js"):
        assert f'src="/static/consent/{script}"' in html


def test_interface_strings_are_escaped() -> None:
    html = render_consent_page("fr").html

    # The apostrophe in "J'accepte" and friends must never break an attribute.
    assert "J&#x27;accepte" in html or "J'accepte" in html
    assert "<script>alert" not in html


@pytest.mark.parametrize("language", ["fr", "en"])
def test_every_placeholder_is_filled(language: str) -> None:
    html = render_consent_page(language).html

    assert "$" not in html, "an unsubstituted template placeholder reached the page"


@pytest.mark.parametrize("language", ["fr", "en"])
def test_policy_sections_are_anchored(language: str) -> None:
    """The table of contents and the anchors depend on these ids."""
    html = render_consent_page(language).html

    assert html.count('class="c-article"') == 11
    for anchor in ("id=\"h-droits\"", "id=\"h-conservation\"", "id=\"h-liberte\""):
        assert anchor in html


def test_french_policy_is_accented() -> None:
    """The previous page shipped 958 words with no accent at all."""
    html = render_consent_page("fr").html

    for word in ("développé", "santé", "données", "sécurité", "législation"):
        assert word in html


def test_the_retention_period_is_stated_in_both_languages() -> None:
    """Section 6 used to ship "[duree a completer]" in production."""
    assert "72 mois à compter de votre dernier échange" in render_consent_page("fr").html
    assert "72 months from your last exchange" in render_consent_page("en").html
    for language in ("fr", "en"):
        assert "c-todo" not in render_consent_page(language).html


def test_client_strings_block_cannot_close_its_tag() -> None:
    html = render_consent_page("fr").html

    block = html.split('data-strings>')[1].split("</script>")[0]
    assert "</" not in block
    assert '"error_invalid_token"' in block


def test_brand_line_is_translated_but_the_name_is_not() -> None:
    """The product name is a name; the words around it are copy."""
    french = render_consent_page("fr").html
    english = render_consent_page("en").html

    assert "par Umbaji" in french
    assert "by Umbaji" in english
    assert "HLlama" in french and "HLlama" in english


def test_nothing_outside_main_stays_french_in_english() -> None:
    """The header, skip link and footer are swapped with the content."""
    english = render_consent_page("en").html

    for french_only in ("par Umbaji", "Aller directement au choix", "Une question ?"):
        assert french_only not in english


def test_footer_carries_the_current_year() -> None:
    """Rendered server side, so the year is right even without JavaScript."""
    html = render_consent_page("fr").html

    assert f"© {datetime.now(timezone.utc).year} Umbaji" in html


def test_theme_control_is_present_and_hidden_until_scripted() -> None:
    html = render_consent_page("fr").html

    assert "data-theme-control" in html
    assert 'role="radiogroup"' in html
    for mode in ("auto", "light", "dark"):
        assert f'data-theme-mode="{mode}"' in html


def test_theme_script_is_not_deferred() -> None:
    """A deferred theme script runs after first paint and the theme flashes."""
    html = render_consent_page("fr").html

    assert '<script src="/static/consent/consent-theme.js"></script>' in html


@pytest.mark.parametrize(
    ("state", "marker"),
    [("used", "link_used"), ("expired", "link_expired"), ("invalid", "link_invalid"), ("missing", "no_token")],
)
def test_a_link_that_cannot_record_says_so_and_hides_the_choice(state: str, marker: str) -> None:
    """She learns the link is spent on opening the page, not on tapping."""
    strings = json.loads(
        (Path(__file__).resolve().parent.parent / "content" / "consent" / "ui.fr.json").read_text(encoding="utf-8")
    )
    html = render_consent_page("fr", state).html

    # Interface strings are escaped on the way in, apostrophes included.
    assert escape(strings[f"{marker}_title"], quote=True) in html
    assert "data-choice hidden" in html


def test_a_valid_link_offers_the_choice() -> None:
    html = render_consent_page("fr", "valid").html

    assert "data-choice hidden" not in html
    assert "J'accepte" in html or "J&#x27;accepte" in html


def test_the_whatsapp_link_carries_no_prefilled_message() -> None:
    """The reply is pushed by the backend now; she has nothing to send, and the
    fragile byte-exact sentence is gone from the page."""
    script = (Path(__file__).resolve().parent.parent / "static" / "consent" / "consent.js").read_text(
        encoding="utf-8"
    )

    assert "?text=" not in script
    assert "consentement" not in script.split("/* The link only reopens")[1].split("*/")[1]


def test_the_policy_is_public_indexable_and_cacheable() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from routes.consent import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    for lang, title in (("fr", "Politique de service et de confidentialité"), ("en", "Service and privacy policy")):
        response = client.get(f"/policy?lang={lang}")
        assert response.status_code == 200
        assert response.headers["content-language"] == lang
        assert "public" in response.headers["cache-control"]
        assert '<meta name="robots" content="index, follow">' in response.text
        assert title in response.text
        assert 'id="decision"' not in response.text
        assert "72" in response.text


def test_the_consent_page_links_to_the_policy() -> None:
    from services.consent_page import render_consent_page

    assert 'href="/policy?lang=fr"' in render_consent_page("fr").html
    assert 'href="/policy?lang=en"' in render_consent_page("en").html
