"""Sheet H2 — the public, indexable page of the HLlama service policy.

Same text as the consent page (content/consent/legal.*.html), without the
decision: anyone can read and link it, search engines can index it, and the bot
can send it in a conversation. The consent page links here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from string import Template

from config import settings
from services.consent_page import (
    DEFAULT_LANGUAGE,
    STATIC_BASE,
    SUPPORTED_LANGUAGES,
    legal_html,
    list_items_html,
    text_of,
    ui_strings,
)

POLICY_PATH = "/policy"
_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "policy.html"


@lru_cache(maxsize=1)
def _template() -> Template:
    return Template(_TEMPLATE_PATH.read_text(encoding="utf-8"))


def policy_url(language: str = DEFAULT_LANGUAGE) -> str:
    """Absolute link to the policy, for the bot and the canonical tag."""
    base = settings.CONSENT_PAGE_BASE_URL.rstrip("/")
    return f"{base}{POLICY_PATH}?lang={language}"


def render_policy_page(language: str) -> str:
    if language not in SUPPORTED_LANGUAGES:
        language = DEFAULT_LANGUAGE
    strings = ui_strings(language)
    return _template().substitute(
        lang=language,
        dir=text_of(strings, "dir") or "ltr",
        document_title=text_of(strings, "policy_document_title"),
        meta_description=text_of(strings, "policy_meta_description"),
        canonical_url=policy_url(language),
        policy_path=POLICY_PATH,
        brand_name=text_of(strings, "brand_name"),
        brand_by=text_of(strings, "brand_by"),
        page_title=text_of(strings, "policy_page_title"),
        page_intro=text_of(strings, "policy_page_intro"),
        version_label=text_of(strings, "version_label"),
        policy_version=text_of(strings, "policy_version"),
        reading_time=text_of(strings, "reading_time"),
        key_points_title=text_of(strings, "key_points_title"),
        key_points_html=list_items_html(strings, "key_points"),
        legal_content=legal_html(language),
        footer_contact=text_of(strings, "footer_contact"),
        footer_rights=text_of(strings, "footer_rights"),
        footer_copyright=text_of(strings, "footer_copyright").replace(
            "{year}", str(datetime.now(timezone.utc).year)
        ),
        lang_group_label=text_of(strings, "lang_group_label"),
        lang_name_fr=text_of(strings, "lang_name_fr"),
        lang_name_en=text_of(strings, "lang_name_en"),
        fr_current=' aria-current="true"' if language == "fr" else "",
        en_current=' aria-current="true"' if language == "en" else "",
        static_base=STATIC_BASE,
    )
