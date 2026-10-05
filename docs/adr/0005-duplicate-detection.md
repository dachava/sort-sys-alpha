# ADR 0005: Exact-content duplicate detection for loose files

## Status
Accepted. Amends PLAN.md section 1's non-goal list.

## Context
PLAN.md originally listed de-duplication as a non-goal for v1. Real usage
against a ~1379-file Downloads folder showed this was costing more than
expected: the same `readme.txt`, `license.txt`, `boot.dol`, `icon.png`, and
installer `.exe` files turned up dozens of times across unrelated ROM packs
and re-downloads. `apply`'s `movefs.unique_target()` already avoids
overwriting (it appends `-2`, `-3`, ... on a name collision), but it has no
concept of content equality -- it would happily file 19 byte-identical
copies of `readme.txt` under 19 different names.

Checking the actual `plan.json` from that run showed 16 distinct name
collisions covering 74 files -- about 58 of those would have landed as ugly
`-N` siblings of a file already filed. That's real, measured clutter, not a
hypothetical one.

The original plan considered here was narrower and structural: detect an
archive (`foo.zip`) sitting next to its own already-extracted folder
(`foo/`), or a folder containing a same-named nested duplicate of itself
(`foo/foo/`). The actual collision data didn't support that shape, though:
several of the biggest offenders (`rufus.exe`, `process-explorer.exe`) were
just the same file downloaded more than once, with no archive or nested
folder involved at all. The real pattern is simpler and more general: any
two files anywhere in `source` with byte-identical content, regardless of
structure.

## Decision
Add exact-content duplicate detection, scoped deliberately narrow:

- Only plain loose files (`items.FileItem`) are considered. A file already
  swallowed into a `FileGroup` (cue/bin, etc.) or a `FolderUnit` (PLAN.md
  4.2b) is left alone -- this is a v1 cut, not a belief that those can't
  also have duplicates.
- Detection never reads archive contents and never compares two separate
  folders tree-for-tree. Those remain non-goals; only loose-file-to-loose-
  file content equality is in scope.
- Cost is bounded: `scan()` already stats every file, so files are first
  grouped by exact size (free -- no extra I/O) before anything is hashed. A
  real SHA-256 (`movefs.hash_file()`, already used for move-integrity
  verification) is only computed for files that already share a size with
  at least one sibling, so the hashing cost scales with the size of the
  actual duplicate-candidate set, not with the size of `source`.
- A confirmed duplicate is never moved and never deleted (hard rule 5 still
  applies in full): it's held in place with a reason naming which file it
  duplicates, the same way an unresolved rule or a stale file is held. It
  also never reaches `identify`/`route`/the LLM tier at all, since there's
  nothing to decide.
- Within a duplicate group, which copy is "the one kept" (the one that
  proceeds through the normal pipeline while its siblings are held) is
  whichever `scan()` happened to list first -- deterministic given a fixed
  directory listing order, but not meaningful beyond that. No attempt is
  made to prefer, e.g., the shorter path or the earlier mtime.

## Consequences
- New module `duplicates.py`: `partition_duplicates(items)` returns
  `(remaining_items, duplicate_holds)`. Called from `plan.build_plan()`
  right after `scan()`, before the main per-item loop.
- `Plan.holds` gains entries with a `"exact duplicate of <path>, left in
  place"` reason; `report.md`'s Held section is where these surface, same
  as any other hold.
- PLAN.md section 1's non-goal list is narrowed (see the edit alongside this
  ADR): de-duplication in general is no longer listed as fully out of
  scope, but folder-level and archive-content dedup explicitly still are.
- If a later milestone wants duplicate detection for `FileGroup`/`FolderUnit`
  members too, that's new scope to flag, not something this ADR already
  covers.
