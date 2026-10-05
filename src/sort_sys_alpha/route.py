"""Routing: rules tier first, LLM tier for everything else. See PLAN.md
section 4.4.

A rule-tier verdict always has confidence 1.0 -- it's either a deterministic
match or it doesn't happen. `route()` (rules only) returns None for anything
it can't place; `resolve()` is the full tier-1-then-tier-2 pipeline plan.py
actually calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .config import Config, Rule
from .identify.audio_video import AUDIO_EXTENSIONS
from .identify.types import Evidence
from .items import FileGroup, FolderUnit, ScanItem
from .llm.backend import LlmError, backend_for

# NES/GB/GBC/GBA/N64/Genesis are verified against a header signature;
# SNES/NDS/.dol-as-wii have no cheap signature (see identify/roms.py), so
# their console assignment is extension-only by design, not a failed check.
EXTENSION_ONLY_CONSOLES = {"snes", "nds", "wii"}

INSTALLER_EXTENSIONS = {".exe", ".msi"}
NOTE_EXTENSIONS = {".txt", ".md"}


@dataclass(frozen=True)
class RouteVerdict:
    category: str
    confidence: float
    reason: str
    name_hint: str | None = None
    suggest_delete: bool = False
    # "llm" is the only source the feedback loop (feedback.py) records --
    # rule verdicts are deterministic and confidence 1.0, so there's nothing
    # for the model to learn from them.
    source: Literal["rule", "llm"] = "rule"


def _rule_matches(rule: Rule, evidence: Evidence) -> bool:
    m = rule.match
    if not (m.true_type or m.ext or m.source_host):
        return False
    if m.true_type and evidence.true_type not in m.true_type:
        return False
    if m.ext and evidence.extension not in m.ext:
        return False
    if m.source_host and evidence.source_host not in m.source_host:
        return False
    return True


def _user_rules(evidence: Evidence, config: Config) -> RouteVerdict | None:
    for rule in config.rules:
        if _rule_matches(rule, evidence):
            return RouteVerdict(rule.folder, 1.0, f"matched config rule -> {rule.folder}")
    return None


def _builtin_rules(evidence: Evidence, config: Config) -> RouteVerdict | None:
    kind = evidence.kind
    details = evidence.details
    allowlist = config.resolved_folder_allowlist()

    if evidence.extension in INSTALLER_EXTENSIONS:
        return RouteVerdict("Installers", 1.0, "installer extension", details.get("ProductName"))

    if kind == "image":
        return RouteVerdict("Images", 1.0, "image file")

    if kind == "audio_video" and evidence.extension in AUDIO_EXTENSIONS:
        return RouteVerdict("Audio", 1.0, "audio file")

    if kind == "pdf":
        return RouteVerdict("Documents", 1.0, "PDF document", details.get("title"))

    if kind == "office":
        return RouteVerdict("Documents", 1.0, "office document", details.get("title"))

    if kind == "text" and evidence.extension in NOTE_EXTENSIONS:
        return RouteVerdict("Documents/Notes", 1.0, "note")

    if kind == "log":
        return RouteVerdict("Documents/Logs", 1.0, "log file")

    if kind == "wii_wad":
        folder = "ROMs/wii"
        if folder in allowlist:
            return RouteVerdict(folder, 1.0, f"Wii WAD (type={details.get('wad_type')})")
        return None

    if kind == "mame_romdef":
        return RouteVerdict(
            "Other",
            1.0,
            "MAME/NeoGeo ROM-set definition file, not a playable ROM",
            details.get("game_title"),
            suggest_delete=True,
        )

    if kind == "archive":
        return RouteVerdict("Archives", 1.0, "archive")

    if kind == "rom":
        console = details.get("console")
        verified = details.get("verified", False)
        if console and (verified or console in EXTENSION_ONLY_CONSOLES):
            folder = f"ROMs/{console}"
            if folder in allowlist:
                return RouteVerdict(folder, 1.0, f"{console} ROM, header-verified={verified}")
        return None

    if kind == "disk_image":
        console = details.get("console")
        if console:
            folder = f"ROMs/{console}"
            if folder in allowlist:
                return RouteVerdict(folder, 1.0, f"{console} disc", details.get("volume_label"))
            return None
        if details.get("disc_kind") == "iso9660":
            return RouteVerdict("ISOs", 1.0, "generic ISO image", details.get("volume_label"))
        if details.get("disc_kind") == "rvz":
            return RouteVerdict("ISOs", 1.0, "Dolphin RVZ compressed disc image, console unknown")
        return None

    if kind == "rom_patch":
        return RouteVerdict("Other", 1.0, "IPS ROM patch, not a playable ROM")

    if kind == "url_shortcut":
        return RouteVerdict("Documents", 1.0, "internet shortcut", details.get("target_url"))

    if kind == "ml_weights":
        return RouteVerdict("Other", 1.0, "ML model weights (safetensors)")

    return None


def route(evidence: Evidence, config: Config) -> RouteVerdict | None:
    return _user_rules(evidence, config) or _builtin_rules(evidence, config)


def resolve(
    item: ScanItem, evidence: Evidence, config: Config
) -> tuple[RouteVerdict | None, str | None]:
    """The full pipeline: rules tier, then the LLM tier for whatever rules
    can't place (PLAN.md 4.4). Returns `(verdict, reason)` -- `reason` is only
    set when `verdict` is None, to explain *why* beyond the generic "no
    matching rule" (for example, the model was unreachable).

    `FileGroup` items skip the LLM tier: `apply()` has no support for moving
    a `FileGroup` as a unit (see `plan._move_root`), so a confident model
    verdict for one would crash rather than hold. `FolderUnit` items already
    carry a category from `subfolders.classify_subfolder` and never reach
    either tier here.
    """
    if isinstance(item, FolderUnit):
        return (
            RouteVerdict(item.category, 1.0, item.reason, suggest_delete=item.suggest_delete),
            None,
        )

    verdict = route(evidence, config)
    if verdict is not None or isinstance(item, FileGroup):
        return verdict, None

    try:
        llm_verdict = backend_for(config).classify(evidence, config)
    except LlmError as e:
        return None, str(e)

    return (
        RouteVerdict(
            llm_verdict.category,
            llm_verdict.confidence,
            llm_verdict.reason,
            llm_verdict.name,
            llm_verdict.suggest_delete,
            source="llm",
        ),
        None,
    )
