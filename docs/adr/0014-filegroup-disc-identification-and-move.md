# ADR 0014: Console detection and move support for disc `FileGroup`s

## Status
Accepted.

## Context
Real Downloads filing was holding every PS1 `.cue`+`.bin` set with "no
matching rule" (`Frogger 2 - Swampy's Revenge`, `Need For Speed II`,
`Panzer Bandit` -- a two-track set, `Raiden Project`). The cause: `groups.py`
bundles a `.cue` sheet and its `.bin` track(s) into a `FileGroup` *before*
identification ever runs, and `identify_item()` never dispatched a
`FileGroup` to `DiskImageExtractor` at all -- it just stamped generic
`disc_group` evidence (group kind, member list, size) with no console
detection whatsoever. `route.py` had no rule for `disc_group`, so
`route()` returned `None`, and `resolve()` deliberately skips the LLM
tier for every `FileGroup` -- previously justified as "because `apply()`
can't move one as a unit" (`plan._move_root()` raised
`NotImplementedError`). Everything dead-ended at "no matching rule."

This was a documented gap, not a bug: `groups.py`'s own docstring says
console identification for group members "is a later milestone," and
PLAN.md 4.2/4.9 always intended `.cue`+`.bin`/`.gdi` groups to move as one
unit once detection existed. CHD support (a compressed container needing
its own reader or a `chdman` shell-out) and `.m3u`/`.ccd` groups are
explicitly **not** part of this change -- separate, genuinely different
formats, left exactly as they behave today.

## Decision
- **Console detection reuses the existing single-disc logic.**
  `disk_images.console_for_members(tracks)` tries each track file in cue
  order, calling the already-existing `console_from_disc_stream()` (the
  same check already used for a disc image sitting inside a zip member)
  on each. The ISO9660 filesystem/`SYSTEM.CNF` only lives on the first
  *data* track; a later CD-DA audio track correctly yields no PVD and is
  skipped, not an error -- this is what makes Panzer Bandit's two-track
  set work. `.gdi` groups get `console = "dreamcast"` unconditionally, no
  byte inspection -- the format is Dreamcast-only by definition.
- **`route.py` gains a `disc_group` branch**, mirroring the existing
  `disk_image` branch exactly: `folder = f"ROMs/{console}"`, checked
  against the allowlist, with a DAT title lookup via the serial read from
  `SYSTEM.CNF` when one exists.
- **Disc groups never reach the LLM tier, same as before -- but now for
  the right reason.** `resolve()`'s `FileGroup` short-circuit stays
  exactly as it was; its justification changes from "apply can't handle
  it" to "disc identification is header/signature detection, which hard
  rule 1 says must stay in the rules tier." `apply()` *can* move a
  `FileGroup` now, but that was never why this stayed rules-only.
- **Every member keeps its own original filename.** A `.cue` sheet's
  `FILE "x.bin" BINARY` lines reference siblings by exact name; renaming
  without rewriting those references would silently corrupt the disc.
  `gate_item()` now branches: for a `FileGroup`, the target filename is
  `item.primary.name` (unchanged), not the templated name every other
  item gets. Only the *folder* changes. A DAT-matched title still
  computes a display `name`/`reason` for the plan/report -- it's just
  never applied to an actual filename.
- **Apply-time atomicity.** "Hold the whole group if any member fails"
  (PLAN.md 4.2) now applies at apply-time, not just at the gate. New
  `apply._apply_group_move()` moves each member in turn, journaling every
  move with the existing `append_entry()`/`move_path()`/`unique_target()`
  -- no new journal primitives needed, since `journal.undo_run()` already
  reverses any number of independent `(source, target)` rows per
  `run_id`. If a member's move fails partway through, every already-moved
  sibling is rolled back using the *same* journaled-move primitive in
  reverse (a rollback is just another ordinary move), and the whole group
  is held, never partially filed.
- **`PlanMove` gains `is_group: bool`.** `apply.py`'s `_is_stale()` and
  main loop branch on it; `_move_root()` for a `FileGroup` returns
  `item.primary` instead of raising `NotImplementedError` (that branch is
  now reachable and correct, not dead code).

## Consequences
- The four originally-reported PS1 cue/bin sets now file correctly into
  `ROMs/psx/`, keeping their original filenames.
- `.gdi` (Dreamcast) groups file correctly too, essentially for free --
  no byte inspection needed, and it reuses the exact same move/journal
  machinery.
- `.m3u` (multi-disc playlists) and `.ccd` (img+sub) groups are
  unchanged: still generic `disc_group` evidence with no console, still
  held. Both are genuinely different problems (`.m3u`'s members are
  typically `.cue` files that would need *their own* nested-group
  resolution; `.ccd` is a different header format entirely) -- flagged
  here as open scope, not silently expanded into.
- CHD is unaddressed. Detecting a console inside a CHD means either
  shelling out to `chdman` or implementing a hunk-decompressing reader --
  a separate task, deliberately dropped from this round.
- A disc group's files are never renamed, even when a DAT match gives a
  confident canonical title -- unlike every other ROM category. If a
  future change wants disc groups renamed too, it has to also parse and
  rewrite the `.cue` sheet's `FILE` references, which is new, separate
  scope with real correctness risk (a bad rewrite breaks the disc) --
  not something to fold into a naming-template change casually.
