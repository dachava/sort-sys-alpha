"""Directory scan: find candidate files in the source folder.
See PLAN.md section 4.1.

Only scans the top level of `source`. Subfolder unit/grab-bag classification
(PLAN.md section 4.2b) is M2 scope; for now every subfolder is reported as
skipped rather than silently descended into or silently ignored.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .groups import detect_groups
from .items import ScanItem

PARTIAL_SUFFIXES = {".crdownload", ".part", ".tmp", ".opdownload"}
STATE_DIR_NAME = ".sort-sys-alpha"


@dataclass(frozen=True)
class SkippedItem:
    path: Path
    reason: str


@dataclass(frozen=True)
class ScanResult:
    items: list[ScanItem]
    skipped: list[SkippedItem]


def is_locked(path: Path) -> bool:
    """Best-effort: can we open this for read+write right now?

    On Windows this genuinely detects another process's exclusive lock. On
    Linux (no mandatory locking), this almost never trips — which is exactly
    the right no-op behavior for dev-box testing without a separate adapter.
    """
    try:
        with path.open("r+b"):
            return False
    except OSError:
        return True


def _is_hidden(path: Path) -> bool:
    return path.name.startswith(".")


def scan(config: Config) -> ScanResult:
    source = config.source
    cutoff = time.time() - config.min_age_minutes * 60
    skipped: list[SkippedItem] = []
    candidates: list[Path] = []

    try:
        entries = sorted(source.iterdir())
    except OSError:
        return ScanResult(items=[], skipped=[])

    for path in entries:
        if path == config.dest:
            continue

        if path.is_dir():
            skipped.append(SkippedItem(path, "subfolder (handled in a later milestone)"))
            continue

        if _is_hidden(path):
            skipped.append(SkippedItem(path, "hidden file"))
            continue

        if path.suffix.lower() in PARTIAL_SUFFIXES:
            skipped.append(SkippedItem(path, "partial download"))
            continue

        try:
            st = path.stat()
        except OSError:
            skipped.append(SkippedItem(path, "unreadable"))
            continue

        if st.st_mtime > cutoff:
            skipped.append(SkippedItem(path, "modified too recently"))
            continue

        if is_locked(path):
            skipped.append(SkippedItem(path, "locked"))
            continue

        candidates.append(path)

    return ScanResult(items=detect_groups(candidates), skipped=skipped)
