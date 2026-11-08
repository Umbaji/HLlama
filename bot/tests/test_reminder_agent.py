import os
import threading
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from app import reminder_agent
from app.services.chat_state import reminder_detail_pending

NOW = datetime(2026, 9, 24, 10, 0, tzinfo=timezone.utc)
RECENT = (NOW - timedelta(hours=2)).isoformat()
OLD = (NOW - timedelta(hours=30)).isoformat()


def reminder(kind="pill", last_inbound_at=OLD, **extra):
    item = {
        "id": "r-1",
        "kind": kind,
        "message": "Prendre la pilule",
        "scheduled_at": "2026-09-24T08:00:00Z",
        "telnumber": "22890000000",
        "timezone": "Africa/Lome",
        "last_inbound_at": last_inbound_at,
    }
    item.update(extra)
    return item


class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body if body is not None else {}

    def json(self):
        return self._body


def sent_ok(wamid="wamid.ABC"):
    return FakeResponse(200, {"messages": [{"id": wamid}]})


class PlanDeliveryTests(unittest.TestCase):
    def setUp(self):
        reminder_detail_pending.clear()

    def test_outside_window_uses_the_template_of_the_kind(self):
        env = {"REMINDER_TEMPLATE_PILL": "hllama_rappel_pilule", "REMINDER_TEMPLATE_LANG": "fr"}
        with mock.patch.dict(os.environ, env):
            plan = reminder_agent.plan_delivery(reminder("pill"), "22890000000", NOW)
        self.assertEqual(plan["channel"], "template")
        template = plan["payload"]["template"]
        self.assertEqual(template["name"], "hllama_rappel_pilule")
        self.assertEqual(template["language"]["code"], "fr")
        params = template["components"][0]["parameters"]
        # 08:00 UTC is 08h00 in Lome (UTC+0), the date is formatted locally.
        self.assertEqual(params, [{"type": "text", "parameter_name": "date", "text": "24/09/2026 à 08h00"}])
        # The lock-screen template never carries the reminder text itself.
        self.assertNotIn("pilule", str(template).lower().replace("hllama_rappel_pilule", ""))

    def test_each_kind_reads_its_own_variable(self):
        env = {"REMINDER_TEMPLATE_CYCLE": "t_cycle", "REMINDER_TEMPLATE_APPOINTMENT": "t_rdv"}
        with mock.patch.dict(os.environ, env):
            cycle = reminder_agent.plan_delivery(reminder("cycle"), "1", NOW)
            rdv = reminder_agent.plan_delivery(reminder("appointment"), "1", NOW)
            pill = reminder_agent.plan_delivery(reminder("pill"), "1", NOW)
        self.assertEqual(cycle["payload"]["template"]["name"], "t_cycle")
        self.assertEqual(cycle["payload"]["template"]["components"][0]["parameters"][0]["text"], "24/09/2026")
        self.assertEqual(rdv["payload"]["template"]["name"], "t_rdv")
        self.assertEqual(pill, {"error": "no_template"})

    def test_date_uses_the_user_timezone(self):
        with mock.patch.dict(os.environ, {"REMINDER_TEMPLATE_OTHER": "t"}):
            plan = reminder_agent.plan_delivery(
                reminder("other", timezone="Africa/Lagos"), "1", NOW
            )
        self.assertEqual(
            plan["payload"]["template"]["components"][0]["parameters"][0]["text"],
            "24/09/2026 à 09h00",
        )

    def test_unknown_kind_falls_back_to_other(self):
        with mock.patch.dict(os.environ, {"REMINDER_TEMPLATE_OTHER": "t_other"}):
            plan = reminder_agent.plan_delivery(reminder("weird"), "1", NOW)
        self.assertEqual(plan["payload"]["template"]["name"], "t_other")

    def test_inside_window_sends_neutral_text_and_keeps_detail(self):
        with mock.patch.dict(os.environ, {"REMINDER_DISCREET": "true"}):
            plan = reminder_agent.plan_delivery(reminder("pill", RECENT), "1", NOW)
        self.assertEqual(plan["channel"], "text")
        self.assertEqual(plan["payload"]["text"]["body"], reminder_agent.NEUTRAL_REMINDER_TEXT)
        self.assertEqual(plan["detail"][0]["text"]["body"], "Prendre la pilule")

    def test_inside_window_not_discreet_sends_the_message(self):
        with mock.patch.dict(os.environ, {"REMINDER_DISCREET": "false"}):
            plan = reminder_agent.plan_delivery(reminder("pill", RECENT), "1", NOW)
        self.assertEqual(plan["payload"]["text"]["body"], "Prendre la pilule")
        self.assertEqual(plan["detail"], [])

    def test_window_edges(self):
        just_inside = (NOW - timedelta(hours=23)).isoformat()
        at_limit = (NOW - timedelta(hours=23, minutes=58)).isoformat()
        self.assertTrue(reminder_agent.within_service_window(just_inside, NOW))
        self.assertFalse(reminder_agent.within_service_window(at_limit, NOW))
        self.assertFalse(reminder_agent.within_service_window(None, NOW))
        self.assertTrue(reminder_agent.within_service_window("2026-09-24T09:00:00", NOW))

    def test_feedback_is_sent_as_buttons(self):
        plan = reminder_agent.plan_delivery(reminder("feedback", RECENT), "1", NOW)
        ids = [b["reply"]["id"] for b in plan["payload"]["interactive"]["action"]["buttons"]]
        self.assertEqual(ids, ["FB:usefulness:3", "FB:usefulness:2", "FB:usefulness:1"])

    def test_feedback_template_has_three_quick_replies(self):
        with mock.patch.dict(os.environ, {"REMINDER_TEMPLATE_FEEDBACK": "hllama_avis"}):
            plan = reminder_agent.plan_delivery(reminder("feedback"), "1", NOW)
        components = plan["payload"]["template"]["components"]
        self.assertEqual([c["parameters"][0]["payload"] for c in components], [
            "FB:usefulness:3", "FB:usefulness:2", "FB:usefulness:1",
        ])
        self.assertEqual(plan["detail"], [])

    def test_notice_is_plain_text_inside_window_and_template_outside(self):
        notice = reminder("notice", RECENT, message="Votre paiement a bien été reçu.")
        plan = reminder_agent.plan_delivery(notice, "1", NOW)
        self.assertEqual(plan["payload"]["text"]["body"], "Votre paiement a bien été reçu.")
        with mock.patch.dict(os.environ, {"REMINDER_TEMPLATE_NOTICE": "hllama_notification"}):
            plan = reminder_agent.plan_delivery(reminder("notice", OLD), "1", NOW)
        self.assertEqual(plan["payload"]["template"]["name"], "hllama_notification")
        self.assertNotIn("components", plan["payload"]["template"])


class ProcessReminderTests(unittest.TestCase):
    def setUp(self):
        reminder_detail_pending.clear()
        self.reports = []
        patcher = mock.patch.object(
            reminder_agent, "post_json",
            side_effect=lambda path, body, **_: self.reports.append((path, body)) or FakeResponse(200),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        consent = mock.patch.object(reminder_agent, "get_consent_status", return_value="accepted")
        self.consent = consent.start()
        self.addCleanup(consent.stop)

    def test_reports_sent_with_wa_message_id_in_json_body(self):
        with mock.patch.dict(os.environ, {"REMINDER_TEMPLATE_PILL": "t"}), \
                mock.patch.object(reminder_agent, "send_message", return_value=sent_ok("wamid.42")):
            outcome = reminder_agent.process_reminder(reminder("pill"), NOW)
        self.assertEqual(outcome, "sent")
        self.assertEqual(self.reports, [("/api/bot/reminders/r-1/sent", {"wa_message_id": "wamid.42"})])

    def test_no_template_is_a_failure_not_a_send(self):
        with mock.patch.dict(os.environ, {}, clear=False), \
                mock.patch.object(reminder_agent, "send_message") as send:
            os.environ.pop("REMINDER_TEMPLATE_PILL", None)
            outcome = reminder_agent.process_reminder(reminder("pill"), NOW)
        send.assert_not_called()
        self.assertEqual(outcome, "no_template")
        self.assertEqual(self.reports, [("/api/bot/reminders/r-1/failed", {"error": "no_template"})])

    def test_whatsapp_error_is_reported_truncated_and_without_pii(self):
        error = FakeResponse(400, {"error": {
            "code": 132001, "type": "OAuthException" + "x" * 900,
            "message": "Template does not exist for 22890000000",
        }})
        with mock.patch.dict(os.environ, {"REMINDER_TEMPLATE_PILL": "t"}), \
                mock.patch.object(reminder_agent, "send_message", return_value=error):
            reminder_agent.process_reminder(reminder("pill"), NOW)
        path, body = self.reports[0]
        self.assertEqual(path, "/api/bot/reminders/r-1/failed")
        self.assertTrue(body["error"].startswith("whatsapp_http_400:132001:"))
        self.assertLessEqual(len(body["error"]), 500)
        self.assertNotIn("22890000000", body["error"])

    def test_no_response_is_reported_failed(self):
        with mock.patch.object(reminder_agent, "send_message", return_value=None):
            reminder_agent.process_reminder(reminder("pill", RECENT), NOW)
        self.assertEqual(self.reports, [("/api/bot/reminders/r-1/failed", {"error": "whatsapp_no_response"})])

    def test_refused_consent_is_never_sent(self):
        self.consent.return_value = "refused"
        with mock.patch.object(reminder_agent, "send_message") as send:
            outcome = reminder_agent.process_reminder(reminder("pill", RECENT), NOW)
        send.assert_not_called()
        self.assertEqual(outcome, "no_consent")
        self.assertEqual(self.reports, [("/api/bot/reminders/r-1/failed", {"error": "no_consent"})])

    def test_unknown_consent_leaves_the_claim_to_expire(self):
        self.consent.return_value = None
        with mock.patch.object(reminder_agent, "send_message") as send:
            outcome = reminder_agent.process_reminder(reminder("pill", RECENT), NOW)
        send.assert_not_called()
        self.assertEqual(outcome, "consent_unavailable")
        self.assertEqual(self.reports, [])

    def test_discreet_send_stores_the_detail_for_her_reply(self):
        from app.utils.anonymity import pseudo_id_for

        with mock.patch.object(reminder_agent, "send_message", return_value=sent_ok()):
            reminder_agent.process_reminder(reminder("pill", RECENT), NOW)
        detail = reminder_detail_pending.get(pseudo_id_for("22890000000"))
        self.assertEqual(detail[0]["text"]["body"], "Prendre la pilule")


class SchedulerStartTests(unittest.TestCase):
    def tearDown(self):
        if reminder_agent._scheduler is not None:
            reminder_agent._scheduler.stop()
        reminder_agent._scheduler = None

    def test_start_is_idempotent_even_across_threads(self):
        with mock.patch.object(reminder_agent.ReminderScheduler, "start") as start:
            results = []
            threads = [
                threading.Thread(target=lambda: results.append(reminder_agent.start_reminder_scheduler(object())))
                for _ in range(5)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        start.assert_called_once()
        self.assertEqual(len({id(r) for r in results}), 1)

    def test_can_be_disabled(self):
        with mock.patch.dict(os.environ, {"REMINDER_SCHEDULER_ENABLED": "false"}):
            self.assertIsNone(reminder_agent.start_reminder_scheduler(object()))
        self.assertIsNone(reminder_agent._scheduler)

    def test_poll_once_processes_each_due_reminder_in_app_context(self):
        app = mock.MagicMock()
        scheduler = reminder_agent.ReminderScheduler(app)
        with mock.patch.object(reminder_agent, "fetch_due_reminders", return_value=[reminder(), reminder()]), \
                mock.patch.object(reminder_agent, "process_reminder") as process:
            self.assertEqual(scheduler.poll_once(), 2)
        self.assertEqual(process.call_count, 2)
        self.assertEqual(app.app_context.call_count, 2)


if __name__ == "__main__":
    unittest.main()
