"""Exact-content duplicate detection for loose files. See ADR 0005.

Scoped deliberately narrow: only plain `FileItem`s are considered (a file
already swallowed into a `FileGroup` or `FolderUnit` is left alone), and
only byte-identical content counts -- no archive-content or folder-tree
comparison. Size is free (already stat'd by `scan()`), so it narrows the
candidate set before anything gets hashed: only files that already share an
exact size with a sibling are ever read.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .items import FileItem, ScanItem
from .movefs import hash_file


def partition_duplicates(
    items: list[ScanItem],
) -> tuple[list[ScanItem], list[tuple[Path, str]]]:
    """Returns `(remaining_items, duplicate_holds)`. Each `duplicate_holds`
    entry is a file left untouched in `source` -- never moved, never
    deleted, just reported -- because an earlier item in `items` already has
    byte-identical content. That earlier item is the one that proceeds
    through the normal pipeline; which of a duplicate group that is comes
    down to `scan()`'s listing order, not any deliberate preference.
    """
    by_size: dict[int, list[FileItem]] = defaultdict(list)
    for item in items:
        if isinstance(item, FileItem) and item.path.exists():
            by_size[item.path.stat().st_size].append(item)

    kept_for_hash: dict[str, Path] = {}
    duplicate_of: dict[Path, Path] = {}
    for candidates in by_size.values():
        if len(candidates) < 2:
            continue
        for candidate in candidates:
            digest = hash_file(candidate.path)
            kept = kept_for_hash.setdefault(digest, candidate.path)
            if kept != candidate.path:
                duplicate_of[candidate.path] = kept

    remaining = [
        item for item in items if not (isinstance(item, FileItem) and item.path in duplicate_of)
    ]
    holds = [
        (path, f"exact duplicate of {kept}, left in place")
        for path, kept in duplicate_of.items()
    ]
    return remaining, holds
