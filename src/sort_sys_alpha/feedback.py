"""The feedback loop ("it learns"): routing.jsonl records every LLM-tier
verdict so recent accepted ones can be shown back to the model as few-shot
examples, and so plan edits / undos become corrected or negative examples.
No fine-tuning -- see PLAN.md section 6. Rule-tier verdicts are always
confidence 1.0 and deterministic, so they're never recorded here; the only
point of this module is helping the *model* do better next time.

Append-only, like journal.jsonl/held.log: a correction or undo appends a new
record rather than rewriting history, and `recent_accepted_examples` resolves
that history by taking the latest record per (run_id, move_root).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from .config import STATE_DIR_NAME, Config
from .identify.types import Evidence

ROUTING_FILENAME = "routing.jsonl"
MAX_EXAMPLES = 5

Outcome = Literal["moved", "held", "corrected", "undone"]


class RoutingEntry(BaseModel):
    run_id: str
    timestamp: datetime
    move_root: Path
    backend: str
    model: str
    prompt_version: str
    evidence: dict[str, Any]
    category: str
    name: str
    confidence: float
    reason: str
    suggest_delete: bool = False
    outcome: Outcome


def _routing_path(config: Config) -> Path:
    return config.dest / STATE_DIR_NAME / ROUTING_FILENAME


def append_routing_entry(entry: RoutingEntry, config: Config) -> None:
    path = _routing_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(entry.model_dump_json() + "\n")


def read_routing_entries(config: Config) -> list[RoutingEntry]:
    path = _routing_path(config)
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(RoutingEntry.model_validate(json.loads(line)))
    return entries


def _evidence_summary(evidence: Evidence) -> dict[str, Any]:
    return {
        "original_name": evidence.original_name,
        "extension": evidence.extension,
        "size": evidence.size,
        "true_type": evidence.true_type,
        "kind": evidence.kind,
        "details": evidence.details,
        "source_host": evidence.source_host,
    }


def record_verdict(
    *,
    run_id: str,
    move_root: Path,
    evidence: Evidence,
    category: str,
    name: str,
    confidence: float,
    reason: str,
    suggest_delete: bool,
    outcome: Literal["moved", "held"],
    prompt_version: str,
    config: Config,
) -> None:
    """Called once per LLM-tier verdict at plan time (PLAN.md 4.10): "every
    verdict ever made". `name` is the model's raw proposed slug (the `name`
    field of its JSON reply), not the gate's final templated filename --
    that's what gets shown back as a few-shot example, in the same shape the
    model is asked to produce.
    """
    append_routing_entry(
        RoutingEntry(
            run_id=run_id,
            timestamp=datetime.now(UTC),
            move_root=move_root,
            backend=config.model.backend,
            model=getattr(config.model, config.model.backend).name,
            prompt_version=prompt_version,
            evidence=_evidence_summary(evidence),
            category=category,
            name=name,
            confidence=confidence,
            reason=reason,
            suggest_delete=suggest_delete,
            outcome=outcome,
        ),
        config,
    )


def record_correction(
    run_id: str,
    move_root: Path,
    outcome: Literal["corrected", "undone"],
    config: Config,
    **overrides: Any,
) -> None:
    """A plan edit before `apply`, or an `undo`, turns the original LLM
    verdict into a corrected or negative example (PLAN.md section 6, bullet
    2). A no-op if there's no original LLM-tier entry for this move -- a
    rule-tier move or an already-held item has nothing to correct.
    """
    entries = read_routing_entries(config)
    original = next(
        (e for e in reversed(entries) if e.run_id == run_id and e.move_root == move_root),
        None,
    )
    if original is None:
        return
    updated = original.model_copy(
        update={"timestamp": datetime.now(UTC), "outcome": outcome, **overrides}
    )
    append_routing_entry(updated, config)


def original_categories(run_id: str, config: Config) -> dict[Path, str]:
    """The category each LLM-tier move in `run_id` was filed under at plan
    time, before any human edit to plan.json -- used by `apply` to detect
    edits worth recording as corrections.
    """
    categories: dict[Path, str] = {}
    for entry in read_routing_entries(config):
        if entry.run_id == run_id and entry.outcome == "moved":
            categories[entry.move_root] = entry.category
    return categories


def recent_accepted_examples(config: Config, limit: int = MAX_EXAMPLES) -> list[RoutingEntry]:
    """Recent accepted, non-undone LLM verdicts (PLAN.md section 6, bullet
    1): the latest record per (run_id, move_root), kept only when that
    latest outcome is still "moved" or "corrected" -- an "undone" latest
    outcome means a human reversed it, so it must not come back as an
    example of what to do. Negative ("undone") examples are logged, for
    later analysis, but deliberately never shown to the model in-prompt as
    "don't do this" -- that framing is more likely to confuse a small local
    model than help it.
    """
    latest: dict[tuple[str, str], RoutingEntry] = {}
    for entry in read_routing_entries(config):
        latest[(entry.run_id, str(entry.move_root))] = entry
    accepted = [e for e in latest.values() if e.outcome in ("moved", "corrected")]
    accepted.sort(key=lambda e: e.timestamp)
    return accepted[-limit:]
