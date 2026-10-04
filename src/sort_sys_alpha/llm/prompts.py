"""Versioned system/user prompt templates for the LLM tier. See PLAN.md
section 4.5: "system prompt (rules, folder allowlist, naming style, a few
recent accepted examples) + evidence JSON". `PROMPT_VERSION` lets
routing.jsonl (feedback.py) record which prompt produced a given verdict.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from ..config import Config
from ..feedback import RoutingEntry
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


def build_system_prompt(config: Config, examples: Sequence[RoutingEntry] = ()) -> str:
    categories = ", ".join(sorted(config.resolved_folder_allowlist()))
    prompt = _SYSTEM_TEMPLATE.format(categories=categories)
    if examples:
        prompt += "\n\n" + _render_examples(examples)
    return prompt


def _render_examples(examples: Sequence[RoutingEntry]) -> str:
    lines = ["Recent accepted examples -- evidence, then the verdict that was kept:"]
    for example in examples:
        evidence_json = json.dumps(example.evidence, default=str)
        verdict_json = json.dumps({"category": example.category, "name": example.name})
        lines.append(f"- {evidence_json} -> {verdict_json}")
    return "\n".join(lines)


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
