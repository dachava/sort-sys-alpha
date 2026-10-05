"""The two kinds of thing `scan` can hand downstream: a lone file, or a file
group that must be planned/gated/moved as one unit. See PLAN.md section 4.2.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileItem:
    path: Path


@dataclass(frozen=True)
class FileGroup:
    kind: str  # "cue_bin" | "gdi" | "m3u" | "ccd"
    primary: Path
    members: tuple[Path, ...]  # includes `primary`


@dataclass(frozen=True)
class FolderUnit:
    """A subfolder classified as a coherent unit (PLAN.md section 4.2b):
    it moves intact, as one directory, into `category` — already decided
    by `subfolders.classify_subfolder`, not by the normal route() tier.
    """

    root: Path
    category: str
    reason: str
    members: tuple[Path, ...]  # every file under root, recursively
    # True only when classify_subfolder's "single-type folder" path found
    # every member's own rule-tier verdict agreed on suggest_delete too —
    # see subfolders._single_builtin_category.
    suggest_delete: bool = False


ScanItem = FileItem | FileGroup | FolderUnit
