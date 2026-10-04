"""The response schema the model must return. See PLAN.md section 4.5.

Shared verbatim between Ollama's schema-constrained `format` field and
Lemonade's OpenAI-compatible `response_format` -- same JSON Schema, two
different envelopes around it.
"""

from __future__ import annotations

from pydantic import BaseModel

RESPONSE_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "kind": {"type": "string"},
        "category": {"type": "string"},
        "name": {"type": "string"},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
        "suggest_delete": {"type": "boolean"},
    },
    "required": ["kind", "category", "name", "confidence", "reason"],
}


class LlmVerdict(BaseModel):
    kind: str
    category: str
    name: str
    confidence: float
    reason: str
    suggest_delete: bool = False
