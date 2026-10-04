"""Plan execution: the only command that touches files in `source`.
See PLAN.md sections 4.6 (the stat/hash staleness re-check) and 4.7 (move
semantics). Every move is journaled before it executes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .journal import append_entry
from .movefs import MoveVerificationError, move_path, unique_target
from .plan import Plan, append_held_log


@dataclass(frozen=True)
class ApplyResult:
    moved: list[tuple[Path, Path]]  # (move_root, final_target)
    held: list[tuple[Path, str]]  # apply-time holds: staleness, move errors
    emptied_folders: list[Path]  # grab-bag folders left behind, now empty


def _is_stale(move) -> bool:
    root = move.move_root
    if not root.exists():
        return True
    if root.is_dir():
        current_size = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
        return current_size != move.size
    st = root.stat()
    return st.st_size != move.size or st.st_mtime != move.mtime


def _is_effectively_empty(path: Path) -> bool:
    """True if `path` has no files anywhere under it (empty subfolders don't count)."""
    try:
        return not any(p.is_file() for p in path.rglob("*"))
    except OSError:
        return False


def apply_plan(plan: Plan, config: Config) -> ApplyResult:
    moved: list[tuple[Path, Path]] = []
    held: list[tuple[Path, str]] = []

    for move in plan.moves:
        if _is_stale(move):
            held.append((move.move_root, "file changed between plan and apply"))
            continue

        target = unique_target(move.target)
        append_entry(move.move_root, target, plan.run_id, config)
        try:
            move_path(move.move_root, target)
        except (OSError, MoveVerificationError) as e:
            held.append((move.move_root, f"move failed: {e}"))
            continue
        moved.append((move.move_root, target))

    emptied = [d for d in plan.grab_bag_dirs if d.exists() and _is_effectively_empty(d)]

    append_held_log(held, plan.run_id, "apply", config)
    append_held_log(
        [(d, "left behind empty after sorting; not deleted") for d in emptied],
        plan.run_id,
        "apply",
        config,
    )

    return ApplyResult(moved=moved, held=held, emptied_folders=emptied)
