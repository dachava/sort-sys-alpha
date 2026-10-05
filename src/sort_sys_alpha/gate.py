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
    suggest_delete: bool = False


@dataclass(frozen=True)
class HoldDecision:
    item: ScanItem
    evidence: Evidence | None
    reason: str


GateDecision = MoveDecision | HoldDecision


def _target_extension(item: ScanItem, evidence: Evidence) -> str:
    return "" if isinstance(item, FolderUnit) else evidence.extension


#  A real run showed the model saying "ROMs/ps1" where the config's
# canonical console name (matched against disc BOOT/BOOT2 markers in
# disk_images.py) is "psx" -- a genuinely different word, not a case
# variant, for a console people overwhelmingly call "PS1" in casual
# English. Add to this only on confirmed real-world mismatches, not
# speculatively -- it's a tolerance list, not a general nickname dictionary.
CONSOLE_ALIASES = {"ps1": "psx"}


def _canonical_category(category: str, allowlist: set[str]) -> str | None:
    """`category`, cased exactly as it appears in `allowlist`, or `None` if
    it isn't there even case-insensitively/alias-insensitively. Rule-tier
    verdicts always come straight from allowlist-derived constants, so this
    only ever matters for the LLM tier: nothing guarantees the model echoes
    back the exact vocabulary it was shown in the system prompt, and that's
    not something a prompt change should be relied on to fix (PLAN.md 4.6:
    safety/correctness checks belong in code).
    """
    by_lower = {folder.lower(): folder for folder in allowlist}
    if category.lower() in by_lower:
        return by_lower[category.lower()]

    prefix, sep, console = category.partition("/")
    if sep and prefix.lower() == "roms" and console.lower() in CONSOLE_ALIASES:
        aliased = f"roms/{CONSOLE_ALIASES[console.lower()]}"
        return by_lower.get(aliased)

    return None


def gate_item(
    item: ScanItem,
    evidence: Evidence,
    verdict: RouteVerdict | None,
    config: Config,
    *,
    unresolved_reason: str | None = None,
) -> GateDecision:
    if verdict is None:
        return HoldDecision(item, evidence, unresolved_reason or "no matching rule")

    if verdict.confidence < config.confidence_min:
        reason = f"confidence {verdict.confidence} < {config.confidence_min}"
        return HoldDecision(item, evidence, reason)

    allowlist = config.resolved_folder_allowlist()
    category = _canonical_category(verdict.category, allowlist)
    if category is None:
        return HoldDecision(item, evidence, f"category {verdict.category!r} not in allowlist")

    try:
        name = build_name(evidence, verdict, category, config)
    except NamingError as e:
        return HoldDecision(item, evidence, str(e))

    if not name or name in (".", ".."):
        return HoldDecision(item, evidence, "name is empty or unsafe after slugifying")

    full_name = f"{name}{_target_extension(item, evidence)}"
    target = config.dest / category / full_name

    try:
        target.resolve().relative_to(config.dest.resolve())
    except ValueError:
        return HoldDecision(item, evidence, "target path would escape the destination root")

    return MoveDecision(
        item,
        evidence,
        category,
        full_name,
        target,
        verdict.confidence,
        verdict.reason,
        suggest_delete=verdict.suggest_delete,
    )
