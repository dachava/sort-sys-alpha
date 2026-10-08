# ADR 0010: `{title}` replaces `{date}_{slug}` as the naming default

## Status
Accepted. Starts resolving M8's "naming conventions" open decision.

## Context
The original default template, `{date}_{slug}`, predates DAT matching
(ADR 0007/0008). Once a ROM or disc can carry a real canonical title --
`.Hack - Infection (USA)`, already in exactly the form EmuDeck/RetroArch
and scrapers expect -- slugifying it destroys that on purpose: `slugify()`
lowercases and collapses everything to hyphens, and the template prepends
a move date nobody asked to see, producing
`2026-10-08_hack-infection-usa` instead. The date tells you *when* a file
was filed, not *what* it is, and that's already recoverable from the
file's own timestamp or `journal.jsonl` if it ever mattered.

The user's own framing, after using the tool for a while: the date+slug
default "isn't as useful to help me identify what that file is." Asked
whether this should be a ROM-only fix or apply everywhere, the answer was
everywhere -- there's nothing category-specific about preferring a
readable name over a slug.

## Decision
- **New template field, `{title}`**: the same source `{slug}` already
  used (`verdict.name_hint`, or the original filename's stem) run through
  a new `sanitize_filename()` instead of `slugify()` -- strips only
  Windows-illegal characters (`<>:"/\|?*` and control characters) plus a
  trailing dot/space, and otherwise leaves case, spacing, and punctuation
  untouched. `.Hack - Infection (USA)` round-trips as itself.
- **`NamingConfig.default` changes from `"{date}_{slug}"` to `"{title}"`**,
  for every category, not just ROMs -- a global default change, not a new
  per-category override.
- **`{slug}`/`{date}` both stay available** as template fields for anyone
  who wants a date-prefixed or slugified name for a specific category via
  a custom `[naming]` entry; nothing is removed, only what the *default*
  produces changes.
- **No migration step for already-filed files.** Everything already moved
  under the old `{date}_{slug}` convention keeps its name; this only
  changes what new moves produce going forward. Re-running `plan
  --source` against an already-filed folder (see the `--source` override)
  would compute new names under `{title}` for anything re-triaged, same
  as any other detection improvement.

## Consequences
- Two generically-named, unrelated files that happen to share a title
  (e.g. two different downloads both producing `"notes"`) can now collide
  in the same category folder where the date prefix used to keep them
  apart. `movefs.unique_target()`'s existing `-2`/`-3` suffix handles this
  exactly as it already does for any other name collision -- not a new
  failure mode, just a slightly more common one.
- `gate.py`'s ADR 0009 duplicate-against-destination check still runs
  first for genuinely identical content, so a real re-download still gets
  held rather than becoming a redundant `-2` copy; `{title}` only affects
  what a *non*-duplicate collision gets suffixed from.
- Per-category overrides (does `ROMs` specifically want something beyond
  the bare DAT title, e.g. explicit region tagging when a DAT doesn't
  already bake that in) remain open, separate scope -- this ADR only
  resolves the *default*, not every category's final convention.
