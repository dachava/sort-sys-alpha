# ADR 0009: Duplicate detection against already-filed content

## Status
Accepted. Extends ADR 0005.

## Context
ADR 0005 added exact-content duplicate detection, but scoped to one scan
batch: two byte-identical files found in the same `source` listing. It
says nothing about a file that matches something already sitting in
`dest` from an earlier run.

The user asked directly: after `--source` makes it easy to re-triage an
already-filed folder (e.g. `Archives`, once a detection improvement can
place more of it correctly), or after simply redownloading something they
already have, what happens if the newly-identified item's computed target
name collides with a file already filed?

The answer turned out to be a real gap: `movefs.unique_target()` -- the
function that actually resolves a move's final path -- only checks
whether a *name* already exists at the target, appending `-2`, `-3`, ...
on collision. It has no concept of content equality. A re-download of
something already correctly filed would silently become a second,
byte-identical copy under a different name, right next to the original.
Not destructive (nothing is overwritten or lost), but exactly the kind of
clutter ADR 0005 already exists to prevent -- just from a different
direction (against `dest`, not within one `source` listing).

## Decision
- **New function `duplicates.find_duplicate_in_dest(path, dest_dir)`**,
  alongside ADR 0005's `partition_duplicates` in the same module (same
  size-before-hash cost bound: `dest_dir`'s direct file children are
  stat'd for a size match before anything is actually read with
  `movefs.hash_file()`).
- **Wired into `gate.py`, not `plan.py`.** Unlike ADR 0005's check (which
  runs once per batch, before routing), this needs the move's *computed
  target* -- which category, which name -- so it has to run after
  `build_name()`/the allowlist check, right where `gate_item()` already
  has `target` in hand. A hit returns a `HoldDecision` with reason
  `"exact duplicate of <path>, left in place"`, the same phrasing ADR 0005
  already uses, so both show up identically in `report.md`'s Held section.
- **Scope matches ADR 0005's**: only `FileItem` (loose files). A
  `FolderUnit` move's target is a directory, not a single file alongside
  siblings, so comparing it the same way doesn't apply -- that would need
  `movefs.hash_tree()` against sibling directories, which is new scope,
  not covered here.
- **No config flag.** Per CLAUDE.md's no-feature-flags-for-new-code
  convention: this is just correct behavior, on unconditionally, same as
  every other gate check.
- **Cost**: one directory listing + stat pass over the *target category
  folder* per move candidate (e.g. everything already in `ROMs/genesis`,
  not all of `dest`), hashing only size-matched candidates. Bounded by
  that one folder's size, not the whole filed tree.

## Consequences
- `gate.py` imports `duplicates.find_duplicate_in_dest`; no cycle
  (`duplicates.py` doesn't import `gate.py`).
- This hold reason applies identically regardless of whether the verdict
  came from the rules tier or the LLM tier -- it's a property of the
  computed target, checked after routing decides it, not something either
  tier can bypass.
- Folder-level (`FolderUnit`) duplicate-against-dest detection remains
  open scope, same caveat ADR 0005 already carries forward for its own
  within-batch check.
