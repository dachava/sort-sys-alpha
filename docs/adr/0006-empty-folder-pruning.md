# ADR 0006: `prune` -- a scoped, explicit exception to "never delete"

## Status
Accepted. Amends hard rule 5 and PLAN.md sections 4.2b and 11.

## Context
`plan`/`apply`/`run` already detect which grab-bag folders ended up empty
after a move (PLAN.md 4.2b) and list them in `report.md` under suggested
deletions, but nothing in the codebase ever removes them -- hard rule 5
("never delete") is deliberately absolute for everything that pipeline
touches. In practice, Downloads accumulates empty leftover folders fast:
every extracted archive whose contents got filed away one-by-one, every
grab-bag split down to nothing, every installer run from a folder that's
now just scaffolding. Across several real `plan` runs, review of the
resulting `report.md` showed this clutter growing every run with no way
to clear it short of manually hunting through File Explorer.

The user explicitly asked for this and signed off on relaxing hard rule 5
for it, scoped narrowly: a command that finds folders under `source` that
are empty, or whose entire nested contents (recursively) contain zero
files, and removes them.

## Decision
Add `prune` as a new top-level CLI command, deliberately kept separate
from the plan/apply/run pipeline:

- **Folders only, never files.** `prune` never inspects file content,
  never moves anything, and will not remove a folder that contains a file
  at any depth -- only directories whose entire subtree is empty.
- **Manual, not automatic.** `prune` is its own command, never called by
  `plan`, `apply`, `run`, or the scheduled task. Hard rule 5 still governs
  everything else in the codebase without exception; this is the one
  deliberately scoped carve-out, and it doesn't erode the rule anywhere
  else.
- **No confirmation step.** Per the user's explicit preference, `prune`
  deletes immediately and prints what it removed, rather than a dry-run
  list requiring a second `--yes` pass. The risk is bounded by the first
  bullet: there is no file-loss scenario to confirm against.
- **`dest` and hidden folders are untouched.** `prune` never descends into
  or removes `config.dest` (apply's own destination tree) or any folder
  whose name starts with `.` -- including nested ones, which also blocks
  removal of any ancestor containing them.
- **Not journaled.** `journal.py` exists so a *move* can be undone; an
  empty folder removal has nothing to restore beyond recreating an empty
  directory, so `prune` doesn't write to `journal.jsonl`. Its own output
  (the list of removed paths, printed to stdout) is the only record.

## Consequences
- New module `prune.py`: `prune_empty_folders(config) -> PruneResult`.
  Bottom-up recursion means a folder that only contained now-removed empty
  subfolders is removed in the same pass -- "no files at any nested level"
  resolves correctly without a separate pre-scan.
- New CLI command `prune`, with its own tests in `test_prune.py` plus a
  `test_cli.py` smoke test; `test_subcommands_registered` now includes it.
- `CLAUDE.md` hard rule 5 and `PLAN.md` sections 4.2b/11 are updated to
  name `prune` as the one explicit exception, rather than reading as an
  unconditional "nothing ever deletes anything."
- If a later milestone wants `prune` folded into `run`'s automatic flow,
  or wants a dry-run/confirmation mode, that's new scope to flag and get
  separate sign-off on -- this ADR only covers the manual, no-confirmation
  shape described above.
