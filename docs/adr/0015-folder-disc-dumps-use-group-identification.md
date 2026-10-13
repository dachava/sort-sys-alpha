# ADR 0015: Folder-shaped disc dumps use the same group identification

## Status
Accepted. Amends ADR 0014.

## Context
ADR 0014 gave loose top-level `.cue`+`.bin`/`.gdi` sets real console
detection. A disc dump sitting inside its own subfolder (e.g. `Segagaga
(English v1.1)[GDI]\disc.gdi` + tracks) is a different code path
entirely -- `subfolders.py`'s `classify_subfolder()` -- and still held as
"disc/game dump, console not determined" after that fix landed.

The cause: `_disc_console_category()` routed each folder entry
independently through the ordinary single-file `build_evidence()`, never
through `identify_item()`'s group-aware logic. For `.cue`+`.bin` this
mostly worked by accident -- a loose `.bin` with `SYSTEM.CNF` already
identifies correctly on its own via the regular single-file disk-image
path, group or no group. `.gdi` has no such luck: Dreamcast's console
identity is a property of the `.gdi` sheet's own file format, not
anything readable from a track's bytes, so routing a bare `.gdi` file (no
extractor even claims that extension) or a track in isolation could never
find a console, regardless of ADR 0014.

## Decision
`_disc_console_category()` now groups the folder's entries first, via
the exact same `groups.detect_groups()` `scan()` already uses for a
top-level set, instead of trying each entry independently:
- A `FileGroup` result goes through `identify_item()` + `route()` -- the
  same `cue_bin`/`gdi` detection a loose top-level set gets.
- Anything that stayed ungrouped (no matching sheet, or an ambiguous lone
  `.iso`/`.bin`/`.img`) falls back to the original per-file
  `build_evidence()` check, unchanged.
- `.m3u`/`.ccd` groups still get no console (ADR 0014 never added that),
  so a disc-dump folder built from one of those still correctly holds as
  `unsure` -- this amendment doesn't extend coverage, just wires the
  existing `.cue`+`.bin`/`.gdi` coverage into the folder path too.

A whole-folder move already handles the files correctly once a category
is found -- `apply.py` moves a `FolderUnit` as one atomic directory,
members and filenames untouched -- so no `apply`/`journal` changes were
needed here, unlike ADR 0014's loose-`FileGroup` case.

## Consequences
- A Dreamcast (or PS1 cue/bin) disc dumped into its own subfolder files
  correctly now, same as a loose top-level set.
- `test_disc_sheet_without_identifiable_console_is_unsure`'s fixture
  changed from a (degenerate, never-actually-grouped) `.gdi` to a
  well-formed `.m3u` -- a real `.gdi` no longer belongs in that bucket.
- CDI (DiscJuggler) disc images remain unaddressed in either the loose or
  folder case -- a different, not-yet-studied container format, tracked
  separately.
