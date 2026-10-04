"""Hard safety gates, enforced in code, not in the prompt. See PLAN.md
section 4.6. Every one of these is independent of whatever a model (M3)
would claim — a prompt change must never be the only thing standing
between a low-confidence verdict and a move.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .identify.types import Evidence
from .items import FolderUnit, ScanItem
from .naming import NamingError, build_name
from .route import RouteVerdict


@dataclass(frozen=True)
class MoveDecision:
    item: ScanItem
    evidence: Evidence
    category: str
    name: str
    target: Path
    confidence: float
    reason: str


@dataclass(frozen=True)
class HoldDecision:
    item: ScanItem
    evidence: Evidence | None
    reason: str


GateDecision = MoveDecision | HoldDecision


def _target_extension(item: ScanItem, evidence: Evidence) -> str:
    return "" if isinstance(item, FolderUnit) else evidence.extension


def gate_item(
    item: ScanItem, evidence: Evidence, verdict: RouteVerdict | None, config: Config
) -> GateDecision:
    if verdict is None:
        return HoldDecision(item, evidence, "no matching rule (LLM tier is M3)")

    if verdict.confidence < config.confidence_min:
        reason = f"confidence {verdict.confidence} < {config.confidence_min}"
        return HoldDecision(item, evidence, reason)

    allowlist = config.resolved_folder_allowlist()
    if verdict.category not in allowlist:
        return HoldDecision(item, evidence, f"category {verdict.category!r} not in allowlist")

    try:
        name = build_name(evidence, verdict, verdict.category, config)
    except NamingError as e:
        return HoldDecision(item, evidence, str(e))

    if not name or name in (".", ".."):
        return HoldDecision(item, evidence, "name is empty or unsafe after slugifying")

    full_name = f"{name}{_target_extension(item, evidence)}"
    target = config.dest / verdict.category / full_name

    try:
        target.resolve().relative_to(config.dest.resolve())
    except ValueError:
        return HoldDecision(item, evidence, "target path would escape the destination root")

    return MoveDecision(
        item, evidence, verdict.category, full_name, target, verdict.confidence, verdict.reason
    )
