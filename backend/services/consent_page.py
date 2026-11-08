"""Rendering of the consent page.

The page is content, not code: its legal text, its interface strings and its
markup live in `content/consent/` and `templates/`, so a wording fix is a content
change a reviewer can read as a diff, and never an edit inside a route module.

Rendering uses `string.Template` from the standard library. Jinja2 would be a new
dependency and a new pattern for a single page that needs no loops or conditions.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from html import escape
from pathlib import Path
from string import Template

from config import settings
from services.consent_service import (
    TOKEN_EXPIRED,
    TOKEN_INVALID,
    TOKEN_MISSING,
    TOKEN_USED,
    TOKEN_VALID,
)

DEFAULT_LANGUAGE = "fr"
SUPPORTED_LANGUAGES = ("fr", "en")

_ROOT = Path(__file__).resolve().parent.parent
_CONTENT_DIR = _ROOT / "content" / "consent"
_TEMPLATE_PATH = _ROOT / "templates" / "consent.html"

STATIC_BASE = "/static/consent"
CONSENT_API_PATH = "/api/consent"

# The strings the client script needs for the states it renders on its own.
_CLIENT_STRING_KEYS = (
    "submitting",
    "success_accepted_title",
    "success_accepted_body",
    "success_refused_title",
    "success_refused_body",
    "redirect_countdown",
    "redirect_manual",
    "redirect_blocked",
    "error_title",
    "error_invalid_token",
    "error_already_used",
    "error_network",
    "error_offline",
    "error_generic",
    "retry_label",
)


@dataclass(frozen=True)
class ConsentPage:
    """A rendered page and the language it was rendered in."""

    html: str
    language: str
    link_state: str


def resolve_language(requested: str | None, accept_language: str | None) -> str:
    """Pick a supported language: the query parameter wins, then the header."""
    if requested and requested.lower() in SUPPORTED_LANGUAGES:
        return requested.lower()

    for chunk in (accept_language or "").split(","):
        code = chunk.split(";")[0].strip().lower()[:2]
        if code in SUPPORTED_LANGUAGES:
            return code

    return DEFAULT_LANGUAGE


@lru_cache(maxsize=1)
def _template() -> Template:
    return Template(_TEMPLATE_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=len(SUPPORTED_LANGUAGES))
def ui_strings(language: str) -> dict[str, object]:
    raw = (_CONTENT_DIR / f"ui.{language}.json").read_text(encoding="utf-8")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError(f"ui.{language}.json must hold an object")
    return parsed


@lru_cache(maxsize=len(SUPPORTED_LANGUAGES))
def legal_html(language: str) -> str:
    """Project-owned markup, trusted as written."""
    return (_CONTENT_DIR / f"legal.{language}.html").read_text(encoding="utf-8")


def text_of(strings: dict[str, object], key: str) -> str:
    value = strings.get(key, "")
    return escape(value, quote=True) if isinstance(value, str) else ""


def list_items_html(strings: dict[str, object], key: str) -> str:
    values = strings.get(key, [])
    if not isinstance(values, list):
        return ""
    return "".join(f"<li>{escape(item)}</li>" for item in values if isinstance(item, str))


def _client_strings(strings: dict[str, object]) -> str:
    """JSON for the data block, with `</` neutralised so it cannot close the tag."""
    payload = {key: strings.get(key, "") for key in _CLIENT_STRING_KEYS}
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def _link_state_html(strings: dict[str, object], state: str) -> str:
    """The banner explaining why this link cannot record a decision.

    Rendered server side: the page knows the state of the link before she reads
    the policy, instead of letting her find out when the button fails.
    """
    titles = {
        TOKEN_MISSING: ("no_token_title", "no_token_body"),
        TOKEN_INVALID: ("link_invalid_title", "link_invalid_body"),
        TOKEN_EXPIRED: ("link_expired_title", "link_expired_body"),
        TOKEN_USED: ("link_used_title", "link_used_body"),
    }
    if state not in titles:
        return ""

    title_key, body_key = titles[state]
    return (
        '<p class="c-banner c-banner--warn" role="status">'
        f'<strong>{text_of(strings, title_key)}</strong><br>{text_of(strings, body_key)}'
        f'<br><span class="c-banner__aside">{text_of(strings, "read_only_notice")}</span>'
        "</p>"
    )


def render_consent_page(language: str, link_state: str = TOKEN_VALID) -> ConsentPage:
    """Render the page for a supported language, falling back to French.

    `link_state` comes from the consent service and decides whether the choice
    is offered at all.
    """
    if language not in SUPPORTED_LANGUAGES:
        language = DEFAULT_LANGUAGE

    strings = ui_strings(language)

    html = _template().substitute(
        lang=language,
        dir=text_of(strings, "dir") or "ltr",
        document_title=text_of(strings, "document_title"),
        meta_description=text_of(strings, "meta_description"),
        brand_name=text_of(strings, "brand_name"),
        brand_by=text_of(strings, "brand_by"),
        page_title=text_of(strings, "page_title"),
        page_intro=text_of(strings, "page_intro"),
        version_label=text_of(strings, "version_label"),
        policy_version=text_of(strings, "policy_version"),
        reading_time=text_of(strings, "reading_time"),
        policy_link_label=text_of(strings, "policy_link_label"),
        # Relative: the consent page and the policy are served by the same host.
        policy_href=f"/policy?lang={language}",
        skip_link=text_of(strings, "skip_link"),
        jump_to_decision=text_of(strings, "jump_to_decision"),
        summary_title=text_of(strings, "summary_title"),
        progress_label=text_of(strings, "progress_label"),
        key_points_title=text_of(strings, "key_points_title"),
        key_points_html=list_items_html(strings, "key_points"),
        decision_title=text_of(strings, "decision_title"),
        decision_intro=text_of(strings, "decision_intro"),
        decision_points_html=list_items_html(strings, "decision_points"),
        checkbox_label=text_of(strings, "checkbox_label"),
        accept_label=text_of(strings, "accept_label"),
        accept_hint=text_of(strings, "accept_hint"),
        refuse_label=text_of(strings, "refuse_label"),
        free_choice=text_of(strings, "free_choice"),
        link_state_html=_link_state_html(strings, link_state),
        choice_hidden="" if link_state == TOKEN_VALID else " hidden",
        noscript_message=text_of(strings, "noscript_message"),
        footer_contact=text_of(strings, "footer_contact"),
        footer_rights=text_of(strings, "footer_rights"),
        # Rendered server side so the year is right without JavaScript.
        footer_copyright=text_of(strings, "footer_copyright").replace(
            "{year}", str(datetime.now(timezone.utc).year)
        ),
        theme_label=text_of(strings, "theme_label"),
        theme_auto=text_of(strings, "theme_auto"),
        theme_light=text_of(strings, "theme_light"),
        theme_dark=text_of(strings, "theme_dark"),
        theme_auto_sr=text_of(strings, "theme_auto_sr"),
        theme_light_sr=text_of(strings, "theme_light_sr"),
        theme_dark_sr=text_of(strings, "theme_dark_sr"),
        lang_group_label=text_of(strings, "lang_group_label"),
        lang_name_fr=text_of(strings, "lang_name_fr"),
        lang_name_en=text_of(strings, "lang_name_en"),
        # Marks the active item; the client re-adds the consent token to the
        # links, since the server never sees it.
        fr_current=' aria-current="true"' if language == "fr" else "",
        en_current=' aria-current="true"' if language == "en" else "",
        legal_content=legal_html(language),
        client_strings_json=_client_strings(strings),
        static_base=STATIC_BASE,
        api_path=CONSENT_API_PATH,
        whatsapp_number=escape(settings.CONSENT_WHATSAPP_NUMBER, quote=True),
    )
    return ConsentPage(html=html, language=language, link_state=link_state)
