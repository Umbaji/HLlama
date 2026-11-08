from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from database import get_db
from helpers.anonymity import pseudo_id_for
from helpers.server_message import ServerMessageException, server_message
from schemas.consent import BotConsentLookup, ConsentResponse, ConsentSubmission
from services.bot_auth import verify_bot_api_key
from services.consent_followup import queue_consent_confirmation
from services.user_service import get_or_create_bot_user
from services.consent_page import (
    SUPPORTED_LANGUAGES,
    render_consent_page,
    resolve_language,
)
from services.policy_page import policy_url, render_policy_page
from services.consent_service import (
    ConsentTokenError,
    ConsentTokenUsedError,
    VALID_DECISIONS,
    get_consent_status as consent_status_for,
    get_latest_consent,
    issue_consent_link,
    read_consent_token,
    record_consent,
    token_state,
)

router = APIRouter(tags=["consent"])


# The page carries a consent token in its URL and a decision in its DOM: it must
# not be cached, must not leak the token through a referrer, and needs no
# capability beyond its own two files. Separating the markup from this module is
# what makes a strict policy possible at all.
_PAGE_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; base-uri 'none'; "
        "form-action 'none'; frame-ancestors 'none'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",
}


@router.get("/consent", response_class=HTMLResponse)
def serve_consent_page(
    request: Request,
    lang: str | None = Query(default=None, max_length=8, description=f"One of {SUPPORTED_LANGUAGES}"),
    t: str | None = Query(default=None, max_length=2048, description="Consent link token"),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Serve the consent page.

    It always answers 200: a woman following a stale link still gets to read the
    policy, and the page itself explains that her link can no longer record a
    decision.
    """
    language = resolve_language(lang, request.headers.get("accept-language"))
    # Decided here rather than in the browser: a spent or expired link should
    # say so before she reads 958 words and taps a button that cannot work.
    page = render_consent_page(language, token_state(db, t))
    return HTMLResponse(page.html, headers={**_PAGE_HEADERS, "Content-Language": page.language})


# Public and indexable (sheet H2): no token, nothing personal, safe to cache.
_POLICY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "public, max-age=3600",
}


@router.get("/policy", response_class=HTMLResponse)
def serve_policy_page(
    request: Request,
    lang: str | None = Query(default=None, max_length=8, description=f"One of {SUPPORTED_LANGUAGES}"),
) -> HTMLResponse:
    """Serve the public service and privacy policy: the consent text without the decision."""
    language = resolve_language(lang, request.headers.get("accept-language"))
    return HTMLResponse(
        render_policy_page(language), headers={**_POLICY_HEADERS, "Content-Language": language}
    )


@router.post("/api/consent")
def submit_consent(payload: ConsentSubmission, db: Session = Depends(get_db)):
    if payload.decision not in VALID_DECISIONS:
        raise ServerMessageException("BAD_REQUEST", meta={"detail": "decision doit etre 'accepted' ou 'refused'"})

    try:
        pseudo_id, token_jti = read_consent_token(payload.token)
    except ConsentTokenError:
        raise ServerMessageException("CONSENT_TOKEN_INVALID")

    try:
        record = record_consent(db, pseudo_id, payload.decision, token_jti)
    except ConsentTokenUsedError:
        raise ServerMessageException("CONSENT_TOKEN_ALREADY_USED")

    # She may never come back to WhatsApp, so the confirmation is pushed rather
    # than waited for. A refusal is not pushed: the bot stays silent then.
    if payload.decision == "accepted":
        queue_consent_confirmation(db, pseudo_id)
    return server_message("CONSENT_RECORDED", data=ConsentResponse.model_validate(record).model_dump())


@router.get("/api/bot/consent/{pseudo_id}")
def get_consent_status(pseudo_id: str, db: Session = Depends(get_db), _=Depends(verify_bot_api_key)):
    """Utilise par le bot pour savoir si une utilisatrice a deja repondu au consentement."""
    record = get_latest_consent(db, pseudo_id)
    if not record:
        raise ServerMessageException("CONSENT_NOT_FOUND")
    return server_message("CONSENT_FETCHED", data=ConsentResponse.model_validate(record).model_dump())


def _check_lookup(payload: BotConsentLookup) -> None:
    if pseudo_id_for(payload.telnumber) != payload.pseudo_id:
        raise ServerMessageException("PSEUDO_ID_MISMATCH", status=400)


@router.post("/api/bot/consent/status")
def get_consent_status_for_bot(
    payload: BotConsentLookup, db: Session = Depends(get_db), _=Depends(verify_bot_api_key)
):
    """status is "pending" when she never answered (normal case, not an error)."""
    _check_lookup(payload)
    return server_message(
        "CONSENT_STATUS_FETCHED", data={"status": consent_status_for(db, payload.pseudo_id)}
    )


@router.post("/api/bot/consent/link")
def get_consent_link(
    payload: BotConsentLookup, db: Session = Depends(get_db), _=Depends(verify_bot_api_key)
):
    """Fresh tokenised link to the consent page; the token carries the pseudo_id only.

    The bot only asks for a link because a message just came in, so this is also
    where the backend learns her number and that her WhatsApp window is open. No
    exchange is recorded for a blocked message, and without this the confirmation
    that follows her consent could not be sent.
    """
    _check_lookup(payload)
    user = get_or_create_bot_user(db, payload.pseudo_id, payload.telnumber)
    user.last_inbound_at = datetime.now(timezone.utc)
    db.commit()
    return server_message(
        "CONSENT_LINK_ISSUED",
        # The policy link lets the bot point to the text itself, not only to
        # the page that records a decision (sheet H2).
        data={"url": issue_consent_link(payload.pseudo_id), "policy_url": policy_url()},
    )
