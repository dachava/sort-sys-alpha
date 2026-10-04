"""Routing: rules tier first, LLM tier (M3) for everything else.
See PLAN.md section 4.4.

A verdict with no model call ever has confidence 1.0 — it's either a
deterministic match or it doesn't happen. Anything `route()` can't place
returns None, and the gate holds it with "no matching rule" until the LLM
tier exists.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import Config, Rule
from .identify.audio_video import AUDIO_EXTENSIONS
from .identify.types import Evidence

# NES/GB/GBC/GBA/N64/Genesis are verified against a header signature;
# SNES/NDS have no cheap signature (see identify/roms.py), so their
# console assignment is extension-only by design, not a failed check.
EXTENSION_ONLY_CONSOLES = {"snes", "nds"}

INSTALLER_EXTENSIONS = {".exe", ".msi"}
NOTE_EXTENSIONS = {".txt", ".md"}


@dataclass(frozen=True)
class RouteVerdict:
    category: str
    confidence: float
    reason: str
    name_hint: str | None = None


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
        return None

    return None


def route(evidence: Evidence, config: Config) -> RouteVerdict | None:
    return _user_rules(evidence, config) or _builtin_rules(evidence, config)
