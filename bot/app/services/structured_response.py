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
                        "helpline_request",
                        "agent_action",
                        "health_fact",
                    ],
                },
                "target_language": {"type": "string"},
                "target_format": {"type": "string", "enum": ["text", "audio"]},
                "request_content": {"type": "string"},
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
                "health_fact",
                "health_fact_removed",
                "response",
            ],
            "additionalProperties": False,
        },
    },
}
