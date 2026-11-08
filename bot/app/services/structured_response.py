from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openai.types.shared_params import ResponseFormatJSONSchema

CHAT_RESPONSE_FORMAT: "ResponseFormatJSONSchema" = {
    "type": "json_schema",
    "json_schema": {
        "name": "hllama_response",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "request_type": {
                    "type": "string",
                    "enum": [
                        "question",
                        "translation",
                        "location_request",
                        "reminder",
                        "reminder_update",
                        "helpline_request",
                        "agent_action",
                        "health_fact",
                    ],
                },
                "target_language": {"type": "string"},
                "target_format": {"type": "string", "enum": ["text", "audio"]},
                "request_content": {"type": "string"},
                "scheduled_at": {"type": ["string", "null"]},
                # reminder only; the kinds the backend stores, minus "feedback",
                # which it schedules itself.
                "reminder_kind": {
                    "type": ["string", "null"],
                    "enum": [
                        "cycle",
                        "pill",
                        "injection",
                        "appointment",
                        "notice",
                        "other",
                        None,
                    ],
                },
                "repeat_interval_days": {"type": ["integer", "null"]},
                # reminder only; how often it comes back when she says "every
                # day", "every week" or "every month".
                "repeat_pattern": {
                    "type": ["string", "null"],
                    "enum": ["daily", "weekly", "monthly", None],
                },
                # reminder_update only; the position of the reminder in the
                # list the person was shown.
                "reminder_number": {"type": ["integer", "null"]},
                # health_fact only: what she declared about her health, in her
                # words, and the fact she wants forgotten.
                "health_fact": {"type": ["string", "null"]},
                "health_fact_removed": {"type": ["string", "null"]},
                "response": {"type": "string"},
            },
            "required": [
                "request_type",
                "target_language",
                "target_format",
                "request_content",
                "scheduled_at",
                "reminder_kind",
                "repeat_interval_days",
                "repeat_pattern",
                "reminder_number",
                "health_fact",
                "health_fact_removed",
                "response",
            ],
            "additionalProperties": False,
        },
    },
}
