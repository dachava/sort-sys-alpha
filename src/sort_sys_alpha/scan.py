"""Directory scan: find candidate files in the source folder, and classify
its subfolders. See PLAN.md sections 4.1 and 4.2b.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from .config import STATE_DIR_NAME, Config
from .groups import detect_groups
from .items import ScanItem
from .subfolders import process_subfolder

PARTIAL_SUFFIXES = {".crdownload", ".part", ".tmp", ".opdownload"}

# Re-exported for existing callers (journal.py, plan.py, cli.py) -- the
# constant itself now lives in config.py so feedback.py can use it without
# importing through scan.py's route.py -> llm/ -> feedback.py chain.
__all__ = ["STATE_DIR_NAME", "ScanResult", "SkippedItem", "is_locked", "scan"]


@dataclass(frozen=True)
class SkippedItem:
    path: Path
    reason: str


@dataclass(frozen=True)
class ScanResult:
    items: list[ScanItem]
    skipped: list[SkippedItem]
    grab_bag_dirs: list[Path]


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
    subfolder_items: list[ScanItem] = []
    grab_bag_dirs: list[Path] = []

    try:
        entries = sorted(source.iterdir())
    except OSError:
        return ScanResult(items=[], skipped=[], grab_bag_dirs=[])

    for path in entries:
        if path == config.dest:
            continue

        if path.is_dir():
            if _is_hidden(path):
                skipped.append(SkippedItem(path, "hidden folder"))
                continue
            items, held, grab_bags = process_subfolder(path, config)
            subfolder_items.extend(items)
            skipped.extend(SkippedItem(p, reason) for p, reason in held)
            grab_bag_dirs.extend(grab_bags)
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

        # A plain `st_mtime > cutoff` check is a race at the boundary even on
        # one OS (the file was just written, "now" from two time.time() /
        # stat() calls microseconds apart isn't guaranteed ordered) and
        # proved flaky on Windows CI. min_age_minutes <= 0 means "no minimum
        # age", so skip the comparison entirely rather than relying on which
        # side of a razor-thin boundary the clock lands on.
        if config.min_age_minutes > 0 and st.st_mtime > cutoff:
            skipped.append(SkippedItem(path, "modified too recently"))
            continue

        if is_locked(path):
            skipped.append(SkippedItem(path, "locked"))
            continue

        candidates.append(path)

    items = detect_groups(candidates) + subfolder_items
    return ScanResult(items=items, skipped=skipped, grab_bag_dirs=grab_bag_dirs)
