"""Empty-folder cleanup. See ADR 0006.

A separate, manual command from plan/apply/undo -- hard rule 5 ("never
delete") still applies to everything else in this codebase; this is the
one deliberate, explicitly scoped exception, limited to folders that
contain zero files at any nested depth. It never removes a file, never
touches `dest` (apply's own destination tree), and never descends into or
removes a hidden folder.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import Config


@dataclass(frozen=True)
class PruneResult:
    removed: list[Path]


def _is_hidden(path: Path) -> bool:
    return path.name.startswith(".")


def _prune(root: Path, removed: list[Path]) -> None:
    try:
        entries = list(root.iterdir())
    except OSError:
        return

    for entry in entries:
        if entry.is_dir() and not _is_hidden(entry):
            _prune(entry, removed)

    try:
        if not any(root.iterdir()):
            root.rmdir()
            removed.append(root)
    except OSError:
        pass


def prune_empty_folders(config: Config) -> PruneResult:
    """Remove every folder under `config.source` that is empty, or whose
    entire subtree (recursively) contains no files -- bottom-up, so a
    folder that only contained now-removed empty subfolders is removed in
    the same pass. `config.dest` and hidden folders are left untouched.
    """
    removed: list[Path] = []
    try:
        entries = sorted(config.source.iterdir())
    except OSError:
        return PruneResult(removed=[])

    for entry in entries:
        if entry == config.dest or not entry.is_dir() or _is_hidden(entry):
            continue
        _prune(entry, removed)

    return PruneResult(removed=removed)
