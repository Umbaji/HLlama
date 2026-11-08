import json
import unittest
from unittest import mock

from app.services import button_router, feedback
from app.services.chat_state import (
    feedback_comment_asked,
    feedback_comment_pending,
    reminder_detail_pending,
)
from app.utils.anonymity import pseudo_id_for

WA_ID = "22890000000"


class FakeResponse:
    status_code = 200


def texts(send):
    bodies = []
    for call in send.call_args_list:
        payload = call.args[0]
        payload = json.loads(payload) if isinstance(payload, str) else payload
        bodies.append(payload.get("text", {}).get("body"))
    return bodies


class FeedbackFlowTests(unittest.TestCase):
    def setUp(self):
        for store in (feedback_comment_asked, feedback_comment_pending, reminder_detail_pending):
            store.clear()
        self.posts = []
        patcher = mock.patch.object(
            feedback, "post_json",
            side_effect=lambda path, body, **_: self.posts.append((path, body)) or FakeResponse(),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_rating_is_posted_and_comment_asked_once(self):
        send = mock.Mock()
        self.assertTrue(button_router.route_button_reply(WA_ID, "FB:usefulness:3", send))
        self.assertEqual(self.posts, [("/api/bot/feedback", {
            "pseudo_id": pseudo_id_for(WA_ID), "question_key": "usefulness", "rating": 3, "answer": None,
        })])
        self.assertEqual(texts(send), [feedback.THANKS_TEXT, feedback.COMMENT_QUESTION])

        send.reset_mock()
        button_router.route_button_reply(WA_ID, "FB:usefulness:1", send)
        self.assertEqual(texts(send), [feedback.THANKS_TEXT])

    def test_next_free_text_is_stored_as_comment(self):
        send = mock.Mock()
        button_router.route_button_reply(WA_ID, "FB:usefulness:2", send)
        self.posts.clear()
        send.reset_mock()

        self.assertTrue(feedback.consume_feedback_comment(WA_ID, "Plus d'infos sur la pilule " + "x" * 600, send))
        path, body = self.posts[0]
        self.assertEqual(path, "/api/bot/feedback")
        self.assertEqual(body["question_key"], "comment")
        self.assertIsNone(body["rating"])
        self.assertEqual(len(body["answer"]), 500)
        self.assertEqual(texts(send), [feedback.COMMENT_THANKS_TEXT])

        # Only the message right after the question is a comment.
        self.assertFalse(feedback.consume_feedback_comment(WA_ID, "Une vraie question", send))

    def test_text_without_pending_question_is_not_a_comment(self):
        send = mock.Mock()
        self.assertFalse(feedback.consume_feedback_comment(WA_ID, "Bonjour", send))
        self.assertEqual(self.posts, [])

    def test_malformed_feedback_button_is_ignored(self):
        send = mock.Mock()
        for button_id in ("FB:usefulness:9", "FB:unknown:1", "FB:usefulness:abc", "FB:usefulness"):
            with self.subTest(button_id=button_id):
                button_router.route_button_reply(WA_ID, button_id, send)
        self.assertEqual(self.posts, [])
        send.assert_not_called()

    def test_schedule_is_fire_and_forget_with_short_timeout(self):
        feedback.schedule_feedback(WA_ID, background=False)
        self.assertEqual(self.posts, [("/api/bot/feedback/schedule", {
            "pseudo_id": pseudo_id_for(WA_ID), "telnumber": WA_ID,
        })])

    def test_an_unknown_button_is_left_to_the_caller(self):
        self.assertFalse(button_router.route_button_reply(WA_ID, "XX:1", mock.Mock()))

    def test_other_buttons_are_left_to_the_caller(self):
        self.assertFalse(button_router.route_button_reply(WA_ID, "menu_pharmacie", mock.Mock()))
        self.assertFalse(button_router.route_button_reply(WA_ID, None, mock.Mock()))

    def test_extracts_ids_from_both_button_kinds(self):
        interactive = {"type": "interactive", "interactive": {"type": "button_reply", "button_reply": {"id": "FB:usefulness:3", "title": "Utile"}}}
        template = {"type": "button", "button": {"payload": "menu_pharmacie", "text": "Pharmacie"}}
        self.assertEqual(button_router.extract_button_id(interactive), "FB:usefulness:3")
        self.assertEqual(button_router.extract_button_id(template), "menu_pharmacie")
        self.assertIsNone(button_router.extract_button_id({"type": "text"}))


if __name__ == "__main__":
    unittest.main()
