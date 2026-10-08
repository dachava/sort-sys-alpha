"""Exact-content duplicate detection, loose files only. See ADR 0005/0009.

Two related checks, both scoped deliberately narrow to plain `FileItem`s (a
file already swallowed into a `FileGroup` or `FolderUnit` is left alone),
and both only about byte-identical content -- no archive-content or
folder-tree comparison:

- `partition_duplicates` -- within one scan batch (ADR 0005): two files
  freshly found in `source` with the same content.
- `find_duplicate_in_dest` -- against what's already filed (ADR 0009): a
  single candidate against the files already sitting in its computed
  destination folder, so a re-download of something already correctly
  filed doesn't become a redundant `-2` copy.

Both lean on the same cost-bounding trick: size is free (already stat'd by
`scan()`, or by a plain `Path.stat()` for the destination side), so it
narrows the candidate set before anything gets hashed -- a real SHA-256
(`movefs.hash_file()`) only runs for files that already share a size with
at least one candidate.
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


def find_duplicate_in_dest(path: Path, dest_dir: Path) -> Path | None:
    """A file already in `dest_dir` with content byte-identical to `path`,
    if any (ADR 0009). `dest_dir` not existing yet is the common case (the
    category folder hasn't been created) and is a cheap no-op, not an
    error. Only direct file children of `dest_dir` are considered -- the
    same flat-per-category layout every move already targets.
    """
    if not dest_dir.is_dir():
        return None
    size = path.stat().st_size
    candidates = [p for p in dest_dir.iterdir() if p.is_file() and p.stat().st_size == size]
    if not candidates:
        return None
    digest = hash_file(path)
    return next((c for c in candidates if hash_file(c) == digest), None)
