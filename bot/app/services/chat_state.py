"""Short-lived per-user conversation state, keyed by pseudo_id.

This is per-replica process memory: with several replicas, a reply that lands
on another replica than the one that set the state is handled as a normal
message. Acceptable for "ask a comment once" and "show the reminder detail on
reply"; move it to the backend (or Redis) if the bot is scaled out.
"""
import threading
import time


class TTLStore:
    def __init__(self, ttl_seconds: float, max_items: int = 5000):
        self._ttl = ttl_seconds
        self._max = max_items
        self._items: dict[str, tuple[float, object]] = {}
        self._lock = threading.Lock()

    def set(self, key: str, value: object = True) -> None:
        if not key:
            return
        now = time.monotonic()
        with self._lock:
            if len(self._items) >= self._max:
                self._purge(now)
                if len(self._items) >= self._max:
                    # Drop the oldest entry rather than growing without bound.
                    oldest = min(self._items, key=lambda k: self._items[k][0])
                    self._items.pop(oldest, None)
            self._items[key] = (now + self._ttl, value)

    def get(self, key: str):
        with self._lock:
            entry = self._items.get(key)
            if entry is None:
                return None
            if entry[0] <= time.monotonic():
                self._items.pop(key, None)
                return None
            return entry[1]

    def pop(self, key: str):
        with self._lock:
            entry = self._items.pop(key, None)
        if entry is None or entry[0] <= time.monotonic():
            return None
        return entry[1]

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def _purge(self, now: float) -> None:
        for key in [k for k, (expires, _) in self._items.items() if expires <= now]:
            self._items.pop(key, None)


# Waiting for the free-text answer to the feedback comment question.
feedback_comment_pending = TTLStore(ttl_seconds=30 * 60)
# The comment question was already asked in this feedback round.
feedback_comment_asked = TTLStore(ttl_seconds=24 * 3600)
# Detail of a discreet reminder, shown when the user replies to it.
reminder_detail_pending = TTLStore(ttl_seconds=72 * 3600)
# The last reminder list shown to the user, keyed by pseudo_id, so "annule le
# rappel 2" can resolve the number against what she actually saw. Long enough
# to look at a list and answer, short enough that a stale mapping never
# cancels a reminder she has long forgotten.
reminder_last_list = TTLStore(ttl_seconds=60 * 60)
# The detail of a discreet reminder was just sent to her, so "quel est le
# message ?" right after is already answered and must not reach the model.
reminder_detail_shown = TTLStore(ttl_seconds=10 * 60)
# Her pending reminders, as last read from the backend, so the note given to
# the model on every message does not mean a backend call every time. Two
# minutes: short enough that nothing she did elsewhere stays wrong for long,
# and it is dropped outright whenever a reminder is created or cancelled.
reminder_snapshot = TTLStore(ttl_seconds=120)
# Reminder being prepared in the chat: nothing is created before she confirms.
# Half an hour, because choosing a date takes thought and nothing expires on
# the backend side.
reminder_drafts = TTLStore(ttl_seconds=30 * 60)
# A health fact she declared, waiting for her agreement. Same half hour.
health_fact_drafts = TTLStore(ttl_seconds=30 * 60)
# She was offered the nearest health service, after the emergency numbers. Ten
# minutes is enough to answer "oui".
emergency_offer = TTLStore(ttl_seconds=10 * 60)
# A reminder being moved: which one, and to when. Same half hour.
reminder_update_drafts = TTLStore(ttl_seconds=30 * 60)
# The passages of the documentary base, by question. Five minutes: a woman who
# asks the same thing twice in a row gets the same extracts without a second
# call to the backend.
knowledge_cache = TTLStore(ttl_seconds=5 * 60)

# A request the consent gate intercepted, replayed once she is allowed through.
# An hour is long enough to read the form and decide, short enough that a
# forgotten request never resurfaces out of nowhere.
held_request = TTLStore(ttl_seconds=60 * 60)

# Whether she has already been greeted and asked to consent. The first ask
# introduces HLlama; the ones after it stay short instead of repeating the
# whole presentation at her.
consent_prompt_seen = TTLStore(ttl_seconds=24 * 3600)

# The consent gate turned her away and she has not been let through since. The
# first message that passes the gate is the one after she accepted the form.
consent_gated = TTLStore(ttl_seconds=24 * 3600)

# The kind of place she is looking for, set either by what she wrote or by the
# menu, and read when her location arrives. Half an hour: she has to find the
# attachment button and allow WhatsApp to read her position.
pending_place_category = TTLStore(ttl_seconds=30 * 60)


def awaiting_her_answer(pseudo_id: str) -> bool:
    """Whether the bot has asked her something and is waiting for the answer.

    The menu shortcuts must then stay out of the way: asked "quel montant ?",
    she answers "5" and means five hundred francs, not the fifth menu entry.
    Asked for a reason, she may well write "pharmacie".
    """
    return bool(
        reminder_drafts.get(pseudo_id)
        or reminder_update_drafts.get(pseudo_id)
        or health_fact_drafts.get(pseudo_id)
        or feedback_comment_pending.get(pseudo_id)
    )
