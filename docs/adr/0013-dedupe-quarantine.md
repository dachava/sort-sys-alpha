# ADR 0013: `dedupe` -- quarantining confirmed duplicates, never deleting

## Status
Accepted.

## Context
ADR 0005 and ADR 0009 added exact-content duplicate *detection*, but
deliberately stopped at reporting: a confirmed duplicate is held in place
with a reason, and hard rule 5 ("never delete") means nothing in
`plan`/`apply`/`run`/`rename` ever acts on that hold. In practice this
means a filed tree can accumulate an unbounded number of `"exact
duplicate of X, left in place"` holds that nothing ever clears -- real
usage against an SD card's ROM folders (snes/nes/genesis/gba/gbc/...)
surfaced ~350 such pairs after `rename` was pointed at it: the same ROM
filed twice under two different naming conventions (a clean No-Intro-
style name and an earlier auto-slugified name), byte-identical in both
copies.

The user explicitly asked for this to become real, built-in
functionality, not a one-off script -- but true deletion means rewriting
hard rule 5 itself and superseding both ADR 0005 and ADR 0009's explicit
"never deleted" language. That's a bigger architectural change than the
actual problem needs: the goal is just to get the loser out of the way
of the folder a frontend/emulator actually scans, which a *move* already
accomplishes without touching hard rule 5 at all.

## Decision
- **New command, `dedupe [--path DIR]`.** Same shape as `rename` (ADR
  0012): scoped to `path` if given, else the whole filed tree under
  `dest`. Loose files only (`FileItem`), same boundary as ADR 0005/0009.
- **Groups by content, not name.** `duplicates.group_duplicates()` hashes
  every file under scope (same size-before-hash cost bound as the other
  two checks in that module) and returns every group of two or more
  byte-identical files. A file with no duplicate isn't reported at all.
- **Picks a keeper per group, deterministically.** The member whose stem
  is *not* a fixed point of `naming.slugify()` wins -- a human-readable
  or DAT-matched title (`"Game Title (USA)"`) beats an auto-generated
  slug (`"game-title-usa"`). If every member is a slug, or none are, the
  tie breaks on path sort order. No attempt to score "which title is more
  correct" beyond that one signal.
- **Moves every other member into `dest/_Duplicates/<category>/`**,
  mirroring the file's current category path so the quarantine folder
  stays legible, named via the existing `movefs.unique_target()` so a
  second collision there doesn't overwrite anything either. This is an
  ordinary `PlanMove`, journaled and undoable exactly like any other move
  -- **nothing is ever deleted.** The user empties `_Duplicates` by hand
  (or runs `prune` afterward for the now-empty source folders).
- **Reuses the plan/apply machinery wholesale**, same precedent as ADR
  0012: `build_dedupe_plan()` returns an ordinary `Plan`, written via
  `write_plan()` with a `"dedupe"` label, executed via the existing
  `apply --plan ...`.
- **No `gate_item()` call.** Unlike `rename`, this never identifies or
  routes anything -- it's a pure content-equality decision, so the
  confidence gate and folder allowlist (hard rule 4) don't apply; there's
  no model-originated verdict here to gate against.

## Consequences
- Hard rule 5 is untouched -- no amendment needed, and ADR 0005/0009's
  "never deleted" language still holds in full. `_Duplicates` is just
  another filed location, subject to the same journal/undo machinery as
  everywhere else.
- `_Duplicates` itself is excluded from `dedupe`'s own file walk (and
  `rename`'s), so re-running either command doesn't try to re-quarantine
  or re-rename something already sitting in quarantine.
- This is new scope beyond PLAN.md's M0-M8 milestone list (all of which
  are substantially done) -- maintenance tooling on top of a finished
  roadmap, not a jump ahead to unplanned milestone work.
- If a later request wants actual deletion, that's a deliberate,
  separate decision requiring a hard-rule-5 amendment and a new ADR
  superseding this one -- not something `dedupe` drifts into on its own.
