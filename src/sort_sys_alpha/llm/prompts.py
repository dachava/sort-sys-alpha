"""Versioned system/user prompt templates for the LLM tier. See PLAN.md
section 4.5: "system prompt (rules, folder allowlist, naming style, a few
recent accepted examples) + evidence JSON".

Few-shot examples from accepted history are M5/M6 scope (the feedback loop
needs `routing.jsonl` history, which doesn't exist yet) -- the prompt here
is allowlist + naming style only. `PROMPT_VERSION` exists so routing.jsonl
(once it's written) can record which prompt produced a given verdict.
"""

from __future__ import annotations

import json

from ..config import Config
from ..identify.types import Evidence

PROMPT_VERSION = "v1"

_SYSTEM_TEMPLATE = """You are a file-routing assistant for a local Downloads folder sorter.
Classify the file described in the next message into exactly one of these categories:
{categories}

Naming style: a short, lowercase, hyphen-separated slug with no file extension \
(for example "gl-inet-flint-2-user-guide").

Respond with a single JSON object matching this shape, and nothing else:
{{"kind": "...", "category": "...", "name": "...", "confidence": 0.0, \
"reason": "...", "suggest_delete": false}}

If you can't confidently classify the file, set "confidence" below 0.5 and \
explain why in "reason" rather than guessing."""


def build_system_prompt(config: Config) -> str:
    categories = ", ".join(sorted(config.resolved_folder_allowlist()))
    return _SYSTEM_TEMPLATE.format(categories=categories)


def build_user_message(evidence: Evidence) -> str:
    payload = {
        "original_name": evidence.original_name,
        "extension": evidence.extension,
        "size": evidence.size,
        "true_type": evidence.true_type,
        "kind": evidence.kind,
        "details": evidence.details,
        "source_host": evidence.source_host,
    }
    return json.dumps(payload, default=str)
