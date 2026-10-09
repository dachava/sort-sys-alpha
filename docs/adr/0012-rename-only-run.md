# ADR 0012: `rename` -- recomputing names without recategorizing

## Status
Accepted. Closes the "rename-only runs" item in M8's done-when.

## Context
ADR 0010 made `{title}` the naming default and ADR 0011 extended DAT
matching to single-item archives, but neither helps a file that was
already filed *before* either change landed. The one-off
`strip-date-prefix.ps1` script (a prior stopgap) can only ever strip a
literal date prefix from a filename -- it has no access to the file's
own content, so it can't recover a PDF's real title or pick up a DAT
match that didn't exist when the file was first sorted.

The real fix is to re-run identification against the file's own bytes,
not its stale name. The open question was how to do that without
reopening the much bigger, riskier question of whether the file is even
in the right folder -- `--source` already exists for re-triaging
category, and conflating the two would make a "just fix the name" pass
carry the same risk as a full rescan.

## Decision
- **New command, `rename [--path DIR]`.** Walks already-filed files
  under `dest` (or just `--path` if given), re-runs `identify_item()` +
  `route()` (rules tier only, no LLM) on each one fresh, and recomputes
  its name from today's naming template.
- **Never recategorizes.** `gate_item()` is reused wholesale for every
  existing safety check (confidence floor, name safety, the ADR 0009
  duplicate-against-dest check), but its resulting category is compared
  against the file's *current* folder. A mismatch is held with an
  explicit "re-triage with `--source` instead" reason, never silently
  acted on. This is the one rule layered on top of `gate_item()` that it
  doesn't know about itself.
- **Reuses the plan/apply machinery wholesale**, not new infrastructure:
  `build_rename_plan()` returns an ordinary `Plan` (each rename is a
  `PlanMove` with `move_root` = current path, `target` = the recomputed
  path in the *same* folder), written via the existing `write_plan()`
  with a `"rename"` label (or `"rename-<folder>"` with `--path`), and
  executed via the existing `apply --plan ...` -- journaled, undoable,
  never-overwrite, identical to any other move.
- **Files only, not `FolderUnit`s.** A whole filed subfolder's own name
  is out of scope here, same boundary ADR 0009's duplicate check already
  draws.
- **Rules tier only, no LLM.** Keeps a whole-tree run fast and free;
  nothing here depends on a model being reachable.

## Consequences
- Two already-filed files that happen to be byte-identical get held on
  *both* sides when either is reconsidered for a rename -- the ADR 0009
  check runs per file, and each one finds the other already sitting in
  the same folder. Not destructive, just an honest "something's off
  here" rather than picking a winner between two pre-existing files.
- A file whose current name already matches what today's template would
  produce is silently skipped -- it never appears in `moves` or `holds`,
  since there's nothing to report.
- Per-category naming overrides (still open, per PLAN.md section 11)
  apply here exactly as they do for a normal `plan`, since both go
  through the same `naming.build_name()`.
