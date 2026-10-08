# Module reference

A per-file technical reference: what each module does, the intricacies
worth remembering, and exactly what its tests cover. `how-it-works.md` is
the narrative; this is the lookup table for "wait, how does *that* actually
work, and is it tested?"

Every test file lives in `tests/`, named `test_<module>.py` (identify
extractors are `test_identify_<name>.py`). Test names below are the actual
function names — they're written to be read as a sentence.

## Table of contents

- [Entry point & config](#entry-point--config)
- [Core pipeline](#core-pipeline)
- [Supporting pipeline modules](#supporting-pipeline-modules)
- [`identify/` — the extractor plugins](#identify--the-extractor-plugins)
- [`identify/` — ROM & disc subsystem](#identify--rom--disc-subsystem)
- [`llm/` — the LLM tier](#llm--the-llm-tier)

---

## Entry point & config

### `cli.py`
Typer app wiring every subcommand (`scan`, `plan`, `apply`, `run`, `undo`,
`eval`, `doctor`, `prune`) to the library functions that do the real work —
this file has almost no logic of its own, deliberately. The one piece of
real logic is `_apply_source_override()`: `--source` does
`config.model_copy(update={"source": source.expanduser()})` rather than
mutating config in place, so the override only ever affects the `Config`
object passed to that one call, never the file on disk. `plan`/`run` pass
`source.name` as `write_plan()`'s `label`, so an overridden run's output
files are named after the overridden folder instead of colliding with a
normal run's `plan.json`/`report.md`. `_progress`/`_resolved` print to
*stderr*, not stdout, specifically so a script piping `plan`'s final
summary line isn't polluted by the per-item progress output.

**Tests** (`test_cli.py`): `test_help`/`test_subcommands_registered` pin
the CLI surface; one test per command exercises it end-to-end against a
real temp directory (`test_scan_reports_a_file`,
`test_plan_writes_plan_and_report`, `test_run_in_plan_mode_never_touches_source`,
`test_run_in_auto_mode_moves_files`, `test_plan_then_apply_then_undo`,
`test_prune_removes_empty_folders`, `test_doctor_reports_backend_reachability`).
`test_plan_source_override` specifically checks the labeled-output
behavior (`report-Archives.md` exists, plain `report.md` doesn't).
`test_apply_without_a_plan_fails_cleanly` and
`test_undo_with_no_runs_fails_cleanly` cover the "nothing to do yet" exit
paths.

### `config.py`
The pydantic schema for `config.toml`, and the one piece of code that
enforces hard rule 2 ("local only"): `Config.model_post_init` calls
`_check_model_locality()`, which raises unless the *active* backend's
`base_url` hostname is in `LOOPBACK_HOSTS`, or `model.allow_remote` is
explicitly `true`. `resolved_folder_allowlist()` expands the single
`"ROMs/<console>"` placeholder in `folders.allow` into one real entry per
configured console — the allowlist the gate actually checks is never the
literal placeholder string. `RomsConfig.dat_files` has its own
`field_validator(mode="before")` that expands `~` in each path, same as
`source`/`dest`. `STATE_DIR_NAME` lives here rather than in `scan.py`
specifically to avoid an import cycle: `feedback.py` needs it, and
`scan.py` already imports `route.py` → `llm/` → `feedback.py`.
`load_config()` strips a UTF-8 BOM before handing bytes to `tomllib`,
since several common ways of writing a file on Windows (Notepad, legacy
`-Encoding utf8` in Windows PowerShell 5.1) emit one and `tomllib` treats
it as a syntax error rather than stripping it.

**Tests** (`test_config.py`): `test_rejects_non_loopback_active_backend_url` /
`test_only_checks_the_active_backend` / `test_allow_remote_permits_non_loopback`
cover the locality check precisely (including that it only ever looks at
whichever backend is actually selected). `test_resolved_folder_allowlist_expands_rom_consoles`
confirms the placeholder expansion. `test_load_strips_a_leading_utf8_bom`
and `test_load_missing_path_returns_defaults` cover the loader's edge
cases. `test_sample_config_in_plan_is_valid_toml` parses PLAN.md's own
documented config example as a regression guard — if that example ever
drifts out of sync with the real schema, this test catches it.

---

## Core pipeline

### `scan.py`
Walks `config.source` one level deep (`source.iterdir()` — subfolders get
delegated to `subfolders.process_subfolder`, not walked directly here).
Per top-level entry: skip the literal `config.dest` path, skip hidden
files/folders, skip partial-download suffixes
(`.crdownload`/`.part`/`.tmp`/`.opdownload`), skip anything younger than
`min_age_minutes`, skip anything `is_locked()` reports as held open by
another process. `is_locked()` is a genuine Windows file-lock check
(`open(path, "r+b")` fails if another process holds an exclusive handle)
that's naturally a no-op on Linux, since Linux doesn't have mandatory
locking — exactly the Linux-fake-adapter pattern CLAUDE.md asks for,
without needing an actual `if platform.system()` branch. The
`min_age_minutes > 0` guard exists because a plain `mtime > cutoff`
comparison is a race at the exact boundary (two `time.time()`/`stat()`
calls aren't guaranteed strictly ordered), which actually caused flakiness
on Windows CI — `min_age_minutes <= 0` now skips the comparison outright
rather than trusting which side of a razor-thin line the clock lands on.

**Tests** (`test_scan.py`): `test_skips_partial_downloads`,
`test_skips_recently_modified_files` / `test_old_enough_file_is_picked_up`
(the boundary pair), `test_min_age_zero_never_holds_on_the_boundary`
(the flakiness fix itself, pinned), `test_skips_hidden_files`,
`test_dest_folder_itself_is_never_scanned`,
`test_a_unit_subfolder_becomes_one_folder_unit_item` /
`test_a_grab_bag_subfolder_is_split_into_its_files` (subfolder delegation),
`test_groups_are_detected_across_top_level_files`.

### `groups.py`
Detects the four sheet-defined file groups (`.cue`+tracks, `.gdi`+tracks,
`.m3u`+discs, `.ccd`+`.img`+`.sub`) from the *text* of the sheet file —
never the track bytes themselves (that's `identify/discs.py`'s job, a
different milestone concern). `_tokens()` splits a sheet line on whitespace
but keeps quoted strings intact (`"Game (Disc 1).bin"` stays one token,
not several), since `.cue`/`.gdi`/`.m3u` lines routinely quote filenames
with spaces. Matching a token to an actual file is by *name*, case-folded
— `_lookup_by_name()` builds a `{lowercased name: Path}` map once,
reused for every sheet. A `.cue` whose referenced `.bin` doesn't actually
exist produces no group at all (`_group_from_sheet` returns `None` on an
empty `members` list) — it falls through to becoming an ordinary loose
`FileItem`, not a broken group.

**Tests** (`test_groups.py`): one test per sheet kind
(`test_cue_bin_group`, `test_gdi_group_with_quoted_filenames`,
`test_m3u_group`, `test_ccd_group`), plus
`test_cue_without_a_matching_bin_is_not_a_group` (the no-op case) and
`test_unreferenced_files_stay_ungrouped`. `test_identify_item_on_a_group_reports_disc_group`
and `...on_a_file_uses_the_normal_pipeline` cover `identify.identify_item`'s
group-vs-file branch from this module's output.

### `subfolders.py`
The unit/grab-bag/unsure classifier (`how-it-works.md` has the conceptual
walkthrough). The intricacies worth remembering:

- **Disc identification runs first and wins outright**, before any of the
  generic signals are even computed — a romhack release routinely bundles
  a small patcher `.exe`+`.bat` alongside the actual disc dump, and
  without this ordering that incidental extracted-app marker would make
  an otherwise-confirmed disc folder register as "conflicting markers"
  and get held as `unsure` for no good reason.
- **`.cue` is deliberately excluded from `DISC_SHEET_EXTENSIONS`** (the
  set that forces an `unsure` hold when console identification fails) —
  it legitimately pairs with either an album (audio + cue) or a disc dump
  (binary tracks + cue), so treating a bare `.cue` as its own disc signal
  would flag every audio album as ambiguous. It's still *tried* for
  console identification via `DISC_IDENTIFY_EXTENSIONS`, just not trusted
  to force a hold on its own.
- **`.iso`/`.bin`/`.img` are in `AMBIGUOUS_DISC_EXTENSIONS`, not
  `DISC_SHEET_EXTENSIONS`** — these extensions have too many ordinary
  non-disc uses (a save file sitting next to a cartridge ROM, a V8 heap
  snapshot inside an extracted browser build) to treat finding one, alone,
  as meaningful evidence of anything. They're tried for console ID the
  same as the sheet extensions, but failing to identify a console from
  one of these doesn't force an `unsure` hold the way a `.gdi`/`.m3u`/`.ccd`
  does.
- **A script-only folder** (`_is_script_only_folder`: every file's
  extension is in `{.bat, .cmd, .ps1, .sh}`) is treated as an `Installers`
  unit even with zero `.exe` present — this exists specifically for a
  portable tool's helper-script folder when the tool's own `.exe` is a
  sibling loose file elsewhere, not in this folder at all.
- **`_single_builtin_category`** (the "folder of only one file type" path)
  requires at least two files — a lone file trivially satisfies "only one
  type," but wrapping one file in a whole-folder move isn't what that
  signal is supposed to mean. `suggest_delete` on the resulting unit is
  only `True` when *every* member's own rule-tier verdict agreed on it,
  so one junk file among several real ones can't flag the whole folder
  for deletion review.
- **More than one signal firing at once is `unsure`, not a priority
  order** — `classify_subfolder` deliberately doesn't try to rank
  code-project vs. extracted-app vs. album; genuine ambiguity gets held,
  not silently resolved by whichever `if` happened to run first.

**Tests** (`test_subfolders.py`, 22 cases): one test per unit signal
(`test_extracted_app_is_a_unit`, `test_portable_exe_with_batch_helpers_is_a_unit`,
`test_script_only_folder_is_a_unit`,
`test_extracted_app_with_incidental_bin_is_still_a_unit`,
`test_code_project_is_a_unit_in_other`, `test_album_is_a_unit`), the disc
paths (`test_disc_dump_with_identifiable_console_is_a_unit`,
`test_lone_unidentifiable_bin_is_a_grab_bag`,
`test_disc_sheet_without_identifiable_console_is_unsure`,
`test_psx_bin_cue_folder_is_a_unit`,
`test_psx_folder_with_incidental_patcher_still_resolves` — the exact
"disc wins over patcher" ordering above — and
`test_cartridge_rom_with_incidental_bin_splits_as_grab_bag`, confirming a
loose cartridge ROM next to a junk `.bin` doesn't falsely trigger disc
logic), the single-type-folder path (`test_single_type_folder_of_images_is_a_unit`,
`test_single_type_folder_propagates_suggest_delete`,
`test_single_type_folder_requires_every_member_to_agree_on_suggest_delete`),
the negative/limit cases (`test_mixed_folder_with_no_markers_is_grab_bag`,
`test_conflicting_markers_is_unsure`,
`test_exceeds_file_limit_is_held_as_limit`), and the recursive
`process_subfolder` wiring itself (`test_process_subfolder_unit_returns_folder_unit_with_all_members`,
`test_process_subfolder_grab_bag_recurses_into_nested_units`,
`test_process_subfolder_unit_carries_suggest_delete`,
`test_process_subfolder_unsure_is_held_whole`).

### `route.py`
Two tiers: `route()` (rules only, always confidence 1.0 or `None`) and
`resolve()` (rules, then the LLM tier if rules came back empty). The
rules-tier `kind` branches mostly map 1:1 to an `identify/` extractor's
`kind`, with a few intricacies:

- **`kind == "rom"`'s note fallback**: an unverified `genesis`/`fds` guess
  on a note-like extension (`.txt`/`.md`) falls back to `Documents/Notes`
  instead of reaching the LLM with misleading "this might be a ROM"
  evidence — the actual fix for the real `.md`/Genesis collision bug.
- **`kind == "archive"`'s three-step console search**: cartridge-extension
  members first (`single_console_from_members`, listing-only, cheap),
  then a disc image inside the archive
  (`console_from_zip_members`, reads member bytes, zip-only), then MSX's
  filename-corroborated `.rom` check (`msx_console_from_archive`) — in
  that order, each a no-op if the previous step already found a console.
- **`kind == "disk_image"`'s DAT lookup**: only attempted when a serial
  was actually read (PS1/PS2/PSP); the matched title replaces the ISO
  volume label as `name_hint`, never changes the category.
- **`CONSOLE_ALIASES`** (currently just `{"ps1": "psx"}`) exists because a
  real LLM-tier run said `"ROMs/ps1"` where the config's own canonical
  name is `"psx"` — a genuinely different word for the same thing in
  casual English, not a case variant `_canonical_category`'s lowercasing
  would already catch. It's explicitly a tolerance list for confirmed
  real mismatches, not a general nickname dictionary to extend
  speculatively.
- **`resolve()`'s `FileGroup` short-circuit**: a `FileGroup` never reaches
  the LLM tier at all, because `apply.py`/`plan._move_root` has no
  implementation for moving a `FileGroup` as a unit — a confident model
  verdict for one would crash rather than hold. `FolderUnit`s never reach
  either tier here; they arrive with a category already decided by
  `subfolders.classify_subfolder`.

**Tests** (`test_route.py`, 44 cases — the largest test file in the repo):
covers every rule-tier branch individually, the full `.md`/Genesis
collision pair (`test_unverified_genesis_md_falls_back_to_note` /
`test_verified_genesis_rom_with_md_extension_still_routes`), every DAT
scenario (match and no-match, for both disc serial and cartridge CRC32),
every archive scenario (single-console zip/7z, mixed-console zip stays
`Archives`, a zip with a disc image inside, the MSX name-corroboration
pair, the README.md-false-positive pair
`test_zip_with_only_readme_md_stays_archive`/`test_zip_with_header_verified_genesis_md_routes_to_console`),
and the `resolve()`-level tier-dispatch behavior
(`test_resolve_folder_unit_never_calls_the_model`,
`test_resolve_file_group_skips_the_llm_tier`,
`test_resolve_falls_back_to_the_llm_when_no_rule_matches`,
`test_resolve_holds_with_the_llm_error_when_unreachable`).

### `gate.py`
Independent of which tier produced a verdict — this is the actual
enforcement point for hard rule 4. In order: no verdict → hold;
`confidence < confidence_min` → hold; category not in the resolved
allowlist (checked case/alias-insensitively via `_canonical_category`,
but the *stored* category is always the canonical-cased one) → hold;
`build_name()` raises `NamingError` → hold; empty/unsafe name → hold;
`target.resolve().relative_to(config.dest.resolve())` raises `ValueError`
(the target would escape `dest`, e.g. via a `..`-laden name) → hold;
**then**, the newest check, an exact-content duplicate already in
`target.parent` → hold (ADR 0009, `FileItem` only). Only after all of
that does a `MoveDecision` get built. `_canonical_category` is also where
`CONSOLE_ALIASES` (defined in this file, used only here) gets applied.

**Tests** (`test_gate.py`, 11 cases): one test per hold reason in the list
above, plus `test_wrong_case_category_is_normalized_not_held` and
`test_ps1_console_alias_is_normalized_to_psx` (confirming normalization
succeeds rather than holding), and the two newest,
`test_exact_duplicate_of_already_filed_file_is_held` /
`test_same_size_but_different_content_is_not_held_as_duplicate` (proving
the duplicate check is genuinely content-aware, not just size-aware).

### `naming.py`
`build_name()` fills `{date}`/`{slug}`/`{title}` into
`config.naming.template_for(category)`, defaulting to `"{title}"` (ADR
0010) — every category gets a human-readable name by default now, not a
date-prefixed slug. `source` for all three fields is `verdict.name_hint`
when a tier provided one (a DAT title, a PE `ProductName`, an
LLM-proposed name, …), falling back to the original filename's stem.
`slugify()` lowercases, collapses every run of non-alphanumeric
characters to a single hyphen, and strips leading/trailing hyphens — an
all-symbol input becomes the literal string `"untitled"` rather than an
empty slug; it's still available for a custom per-category template, just
no longer what the default produces. `sanitize_filename()` is the
human-readable counterpart: strips only Windows-illegal characters
(`<>:"/\|?*`, control characters) and a trailing dot/space, leaving case,
spacing, and punctuation alone — `.Hack - Infection (USA)` round-trips as
itself, which is the entire point (an EmuDeck/scraper-ready ROM title
surviving the naming step verbatim, not getting slugified into
`hack-infection-usa`). A template referencing a field this module doesn't
fill raises `NamingError`, which `gate.py` turns into a hold — "a naming
template needs a field nobody could fill" is itself one of the documented
hard-rule 4 hold conditions, not a bug.

**Tests** (`test_naming.py`): `test_slugify_basic` (the collapsing/
stripping rules), the `sanitize_filename` set (`test_sanitize_filename_
strips_windows_illegal_characters`, `...keeps_casing_and_punctuation`,
`...strips_trailing_dot_and_space`, `...empty_after_cleaning_is_untitled`),
`test_default_template_uses_original_name_when_no_hint` /
`test_name_hint_takes_precedence` (the fallback order, now asserting the
human-readable `{title}` output), `test_rom_dat_title_is_used_verbatim_not_slugified`
(the actual motivating case), and `test_missing_template_field_raises_naming_error`.

### `plan.py`
Orchestrates one full `scan → identify → route → gate` pass into a
`Plan`. The two things worth knowing beyond the obvious loop:

- **Duplicate partitioning happens before the main loop**, not inside it —
  `partition_duplicates()` runs once on the raw scan items, and its holds
  never touch `identify`/`route`/the LLM at all, since there's nothing to
  decide for a file that's already known to duplicate something else in
  this same batch. `on_item`/`on_resolved`'s `total` only ever counts the
  survivors.
- **`_size_and_mtime()`'s staleness baseline is asymmetric by item type**:
  a single `FileItem`'s own mtime is meaningful and cheap, so it's
  recorded; a `FolderUnit`'s directory mtime reflects the directory entry
  itself, not its contents, so only the *summed size of every member* is
  tracked for those — `apply.py`'s staleness re-check re-sums member
  sizes for a folder rather than comparing a meaningless mtime.
- **`write_plan()`'s `label` parameter** (from `cli.py`'s `--source`
  override) swaps `plan.json`/`report.md` for `plan-<label>.json`/
  `report-<label>.md` — this is the only thing standing between a rescan
  and silently overwriting a normal run's report.

**Tests** (`test_plan.py`): the move/hold split
(`test_build_plan_separates_moves_and_holds`), the unreachable-model hold
(`test_build_plan_holds_with_model_unreachable_reason`), a full LLM-tier
round trip with `fake_llm_server`
(`test_build_plan_routes_a_rule_miss_through_the_llm`), confidence-held
LLM verdicts landing in the routing log
(`test_build_plan_records_a_held_llm_verdict_in_routing_log`), the
against-destination duplicate check working end-to-end through the LLM
tier specifically (`test_build_plan_holds_an_llm_routed_duplicate_of_an_already_filed_file`
— CLAUDE.md's "every new gate.py hold reason needs a fake-server test"
rule, satisfied), progress callbacks and per-item latency recording, the
within-batch duplicate path never reaching the LLM
(`test_build_plan_holds_exact_duplicates_without_touching_the_llm`),
scan-skips surfacing as holds, a non-cp1252-safe filename round-tripping
through `write_plan()` correctly, and `plan.json`'s own JSON round-trip.

### `apply.py`
The only module allowed to touch `source`. `_is_stale()` is the plan/apply
staleness re-check: for a directory (`FolderUnit`), it re-sums current
member file sizes and compares against the plan's recorded total; for a
single file, it compares both size *and* mtime against what was recorded
at plan time. A hand-edit to `plan.json`'s `category` field before
`apply` runs is detected by comparing against `feedback.original_categories()`
(what the routing log said at plan time) and logged as a correction — but
only for moves that actually had an LLM-tier routing-log entry in the
first place; a rule-tier move has nothing in the routing log to compare
against, so an edit to one of those is silently honored, not flagged as a
"correction" (there was no model verdict to correct). `emptied_folders`
is computed from `plan.grab_bag_dirs` *after* every move has run, using
`_is_effectively_empty()` (no files anywhere under it, recursively — an
empty nested subfolder doesn't count as "still has something in it").

**Tests** (`test_apply.py`): the move + journal entry
(`test_apply_moves_a_file_and_journals_it`), both staleness cases
(`...skips_a_file_that_changed_since_plan`, `...skips_a_file_removed_since_plan`),
name-collision handling at apply time
(`test_apply_handles_collisions_with_a_suffix`), a whole `FolderUnit`
moving intact, the emptied-grab-bag reporting and its negative case
(`test_apply_does_not_report_a_grab_bag_folder_with_a_held_file` — a
folder with even one held file left behind isn't "emptied"), the
correction-recording pair
(`test_apply_records_a_correction_when_the_plan_category_was_hand_edited` /
`...does_not_record_a_correction_when_the_category_is_unchanged`), and
the cross-volume copy+verify+remove fallback.

---

## Supporting pipeline modules

### `items.py`
Three frozen dataclasses, no logic: `FileItem` (one path), `FileGroup`
(`kind` + `primary` + every `members` path including primary), `FolderUnit`
(`root` + `category` + `reason` + every member file recursively +
`suggest_delete`). `ScanItem` is the `FileItem | FileGroup | FolderUnit`
union everything downstream pattern-matches on. No dedicated test file —
these types are exercised indirectly by every other module's tests.

### `movefs.py`
The actual move primitives, shared by `apply.py` and `undo`.
`move_path()` tries `source.rename(target)` first (same-volume, atomic);
on `OSError` (the cross-volume case) it falls back to copy-then-verify-
then-remove: `shutil.copytree`/`copy2`, re-hash (`hash_tree()` for a
directory — path-relative-to-root plus content, so two directories with
identical files in different *relative* layouts hash differently —
`hash_file()`'s plain SHA-256 for a single file), and only unlink the
source if the hash matches; a mismatch removes the half-written copy and
raises `MoveVerificationError` rather than leaving a silently-corrupted
target around. `unique_target()` is the name-collision resolver — `-2`,
`-3`, ... — and has **no concept of content equality**; that's precisely
the gap ADR 0009's `duplicates.find_duplicate_in_dest` exists to catch
*before* a move ever reaches this function.

**Tests** (`test_movefs.py`): the collision-suffix behavior
(`test_unique_target_returns_same_path_if_free` /
`...suffixes_on_collision`), same-volume rename and whole-directory move,
`hash_file`'s content-dependence and `hash_tree`'s structure-dependence
(two dirs with the same files at different relative paths hash
differently), and `test_move_verification_error_on_corrupted_copy`
(the copy-then-verify failure path, forced by corrupting the destination
mid-copy in the test).

### `journal.py`
Append-only `journal.jsonl`: one `JournalEntry` (`run_id`, `timestamp`,
`source`, `target`) per move, written by `apply.py` *before* `move_path()`
runs. `undo_run()` reverses every entry for a run_id, **most recent
first** (`reversed(entries)`) — not plan order — and is defensive about a
changed world: skip with a message if the target no longer exists, skip
if something's already sitting at the original source path (never
overwrite on undo either). A successful undo calls
`feedback.record_correction(..., "undone", ...)` — the feedback loop's
negative-example path.

**Tests** (`test_journal.py`): append/read round-trip, `last_run_id`,
a full restore, both skip cases
(`test_undo_skips_if_source_already_exists`,
`...skips_if_target_already_gone`), the feedback hook firing on undo
(`test_undo_records_an_undone_correction_for_an_llm_verdict`), and the
most-recent-first ordering itself
(`test_undo_reverses_in_most_recent_first_order`).

### `notify.py`
A single `notify(title, message)` that shells out to
`scripts/windows/notify.ps1` via `powershell.exe` — a no-op immediately on
any non-Windows `platform.system()`. Every failure mode (PowerShell
missing, the subprocess erroring, a 10-second timeout) is caught and
printed to stderr rather than propagated, because a notification failure
must never fail an actual `run`.

**Tests** (`test_notify.py`): the non-Windows no-op, a mocked
`subprocess.run` call to confirm the right PowerShell invocation on
"Windows" (platform patched for the test), and both swallowed-failure
paths (a subprocess error, a timeout).

### `prune.py`
The one explicit, scoped exception to hard rule 5. `_prune()` recurses
depth-first and removes a directory bottom-up only if, after recursing
into every subdirectory first, `not any(root.iterdir())` — i.e. truly
nothing left, files or folders. `prune_empty_folders()` walks
`config.source`'s *top-level* entries only (recursion happens inside
`_prune` per top-level folder), explicitly skipping `config.dest` and
anything hidden — a hidden folder is never descended into, so a hidden
folder containing files below it will correctly block its own non-hidden
ancestor from being considered empty too (the ancestor's `iterdir()`
still sees the hidden child present).

**Tests** (`test_prune.py`): a lone empty folder, a multi-level empty
nested structure, a file at any depth blocking removal, a sibling file
protecting only its own branch (not unrelated empty folders elsewhere),
`dest` is never touched, hidden folders are never touched, and the subtle
one — `test_hidden_folder_blocks_its_ancestor_from_removal` — a hidden
folder with a file inside correctly keeps its *parent* from being
considered empty.

### `duplicates.py`
Covered in depth in `how-it-works.md`'s "Duplicates" section and ADRs
0005/0009. Both functions share the same size-before-hash cost bound.

**Tests** (`test_duplicates.py` for `partition_duplicates`; the
dest-against check is tested through `gate.py`/`plan.py` instead, since
it needs a computed target, not just a list of items): two identical
files (one kept, one held), same-size-different-content is *not* flagged,
a three-way duplicate group keeps only the first, `FileGroup`/`FolderUnit`
items pass through untouched regardless of content, and a lone file isn't
a duplicate of anything.

### `feedback.py`
Append-only `routing.jsonl`, written **only** for LLM-tier verdicts —
rule-tier hits are deterministic by construction, so there's nothing for
a model to learn from logging them. `record_correction()` is a careful
no-op when there's no original LLM-tier entry for that `(run_id,
move_root)` — a rule-tier move or an already-held item has nothing to
correct, so neither a plan-edit nor an undo on one of those writes
anything here. `recent_accepted_examples()` resolves history to the
*latest* record per `(run_id, move_root)` and only keeps ones whose latest
outcome is still `"moved"` or `"corrected"` — critically, an `"undone"`
latest outcome is excluded from few-shot examples, but **not** deleted;
undone verdicts stay in the log for later analysis, just never shown back
to the model in-prompt (a small local model is more likely to get
confused than helped by a "don't do this" framing).

**Tests** (`test_feedback.py`): a basic round-trip, latency recording
and backward-compatible reading of entries written before the `latency_s`
field existed, held verdicts correctly excluded from "accepted," both the
undone-exclusion and corrected-inclusion cases for few-shot examples, the
`limit` parameter, the correction-is-a-noop-without-an-original case, and
`original_categories()` only ever returning entries whose outcome was
`"moved"` for that specific run.

### `evaluate.py`
The `eval` command's harness. Each fixture in `evals/manifest.toml` is
run through the *real* `route.resolve()` pipeline, not a direct backend
call — deliberately, so `eval` stays honest about what an actual run
would do, and `EvalResult.tier` becomes a sanity check that a fixture
hasn't started getting caught by a rule added since it was written (if a
fixture meant to exercise the LLM tier starts showing `tier == "rule"`,
that's a signal to rename it, not a silent change in what's being
measured). `render_report()` separately surfaces LLM-only latency
statistics (mean/median), since rule-tier hits are sub-millisecond and
would otherwise wash out any real latency signal.

**Tests** (`test_evaluate.py`): manifest loading (missing file raises,
valid file parses), an LLM hit being marked correctly, a held case
reporting its hold reason, the full report format (accuracy by category,
overall, latency stats, the rule-tier-contamination note, and held-case
listing), progress callback firing per case, and the empty-results report
text.

---

## `identify/` — the extractor plugins

Every extractor shares the same two-method contract
(`identify/base.py`'s `Extractor`): `can_handle(evidence) -> bool`,
`extract(path, evidence) -> dict`. `identify/__init__.py`'s
`build_evidence()` runs the three universal signals first — `stats.py`
(name/extension/size/dates, zero dependencies), `magic.py` (true MIME
type via `puremagic`, independent of extension — catches a renamed file
or a missing extension), `download_source.py` (Windows
`Zone.Identifier:` ADS → `source_host`/`referrer_host`, a clean no-op on
any other OS since the stream simply doesn't exist there) — then tries
every registered extractor **in ascending `priority` order**, first match
wins, no byte-level tiebreak between two extractors that could both claim
the same file. This "first match wins" design is exactly what made the
`.md`/Genesis collision possible in the first place (`RomExtractor`
claims `.md` ahead of `TextExtractor`), and it's why several extractors
below identify by *content*, not just extension, specifically to avoid
false-claiming a file that happens to share an extension with something
else.

`identify_item()` handles the two non-`FileItem` cases specially: a
`FolderUnit`'s evidence is synthesized directly (`kind = "folder_unit"`,
details carry the category/reason/members already decided by
`subfolders.py` — no extractor dispatch happens for a folder at all), and
a `FileGroup`'s evidence describes the group as a whole (`kind =
"disc_group"`) rather than whatever generic extractor would otherwise
claim the *defining* sheet file (a `.cue` is plain text; its evidence
should say "disc group," not "text file").

Extractors, roughly by priority (lower runs first):

| Priority | Extractor | Claims | Content-verified, or extension-only? |
|---|---|---|---|
| 10 | `RomExtractor` | cartridge ROM extensions | Verified where a cheap header exists (NES/GB/GBC/GBA/N64/Genesis/FDS); extension-only for SNES/NDS/`.dol` |
| 15 | `DiskImageExtractor` | `.iso`/`.img`/`.gcm`/`.nrg`/`.wbfs`/`.rvz`/`.bin` | Verified (magic bytes or ISO9660 filesystem read) |
| 16 | `WiiWadExtractor` | `.wad` | Verified (fixed header-size + type-tag) |
| 20 | `ExecutableExtractor` | `.exe`/`.dll`/`.sys` | Verified (PE parse) |
| 25 | `TorrentExtractor` | `.torrent` | Verified (bencode parse) |
| 30 | `FontExtractor` | `.ttf`/`.otf`/`.ttc`/`.woff`/`.woff2` | Verified (TTF/OTF parse) |
| 32 | `LogExtractor` | `.log`, content-sniffed `.txt` | Content-sniffed for `.txt` |
| 35 | `PdfExtractor` | `.pdf` | Verified (parse) |
| 36 | `OfficeExtractor` | `.docx`/`.xlsx`/`.pptx` | Verified (parse) |
| 40 | `ImageExtractor` | common image extensions | Verified (PIL open) |
| 42 | `AudioVideoExtractor` | audio/video extensions | Verified where tags/ffprobe succeed |
| 44 | `MlWeightsExtractor` | `.safetensors` | Verified (structural check) |
| 44 | `RomPatchExtractor` | `.ips` | Verified (magic bytes) |
| 44 | `UrlShortcutExtractor` | `.url` | Content-sniffed |
| 45 | `MameRomdefExtractor` | `.rc`, content-sniffed | Content-sniffed |
| 45 | `ArchiveExtractor` | `.zip`/`.7z`/`.rar`/tar variants | Listing read for zip/7z/tar; `.rar` extension-only |
| 50 | `TextExtractor` | generic text/code/config extensions | Extension-only (preview is informational, not identification) |
| 1000 | `UnknownExtractor` | everything else | N/A — always matches last |

### `identify/images.py`
PIL for dimensions + EXIF (filtered to a small whitelist of fields:
`Make`/`Model`/`DateTimeOriginal`/`DateTime`/`Software`).
`_looks_like_screenshot()` is two independent signals ORed together: the
filename literally says "screenshot"/"screen shot", *or* the image's
pixel dimensions match a common monitor resolution **and** there's no
camera EXIF (`Make`/`Model`) to suggest otherwise — a real photo at
1920×1080 with camera metadata doesn't get misflagged just because that
resolution happens to also be a common screen size.

**Tests** (`test_identify_images.py`): the resolution-plus-no-EXIF case,
camera EXIF correctly overriding a matching resolution, filename-based
detection working even at a non-matching resolution, and a `.psd` being
claimed as an image at all (PIL can open it, even though it's not a
"normal" photo format).

### `identify/pdf.py`
`pypdf`, with `logging.getLogger("pypdf").setLevel(logging.ERROR)` set at
import time specifically to silence routine xref-table-repair WARNING
logs that would otherwise spam every single `scan`/`plan`/`run` on
real-world (slightly malformed but still parseable) PDFs. `is_scanned` is
just "page 1's extracted text, stripped, is empty" — a cheap, specific
signal for "this needs OCR/vision to actually read," not a guess.

**Tests** (`test_identify_pdf.py`): the logging-suppression behavior
itself (`test_pypdf_xref_warnings_are_silenced`), text/page-count
extraction, and unreadable-bytes handled gracefully (empty dict, not a
crash).

### `identify/office.py`
Three different libraries (`python-docx`, `openpyxl`, `python-pptx`), one
small shared helper (`_core_props`) that smooths over them calling the
same concept by different names — `openpyxl`'s `creator` vs.
`docx`/`pptx`'s `author`. `.xlsx` always loads `read_only=True,
data_only=True` (values, not formulas; no write-mode overhead for a file
that's only ever being inspected) and is explicitly `.close()`d in a
`finally` — `openpyxl` holds the zip file open otherwise.

**Tests** (`test_identify_office.py`): one test per format — docx
title+preview, xlsx sheet names, pptx slide titles.

### `identify/text.py`
Pure extension-to-language lookup table plus an 8KB preview — no parsing,
no content sniffing (that's `logs.py`/`mame_romdef.py`/`url_shortcut.py`'s
job for the extensions that need it). `.txt` maps to `language: None`
deliberately — it has no programming language, but it's still a valid
text preview.

**Tests** (`test_identify_text_and_logs.py`, shared with `logs.py`):
`test_python_file_gets_language_and_preview` is this module's half; the
other three test `logs.py`'s content-sniffing instead.

### `identify/logs.py`
`looks_like_log()` samples the first 20 non-blank lines and requires at
least half to match a timestamp pattern (ISO-ish or `MM/DD/YYYY`) or a log
level keyword (`TRACE`/`DEBUG`/`INFO`/`WARN(ING)`/`ERROR`/`FATAL`/
`CRITICAL`) — a ratio, not "any line matches," so a `.txt` that happens to
mention "ERROR" once in a sentence doesn't get misclassified. This is the
only thing that lets a `.txt` file be claimed as a log at all; `.log`
itself is unconditional.

**Tests** (in `test_identify_text_and_logs.py`):
`test_dot_log_file_is_a_log` (unconditional), `test_txt_file_that_is_really_a_log`
(the sniff firing correctly), `test_txt_file_that_is_just_notes` (the
negative case — plain prose doesn't trip it).

### `identify/executables.py`
`pefile`, `fast_load=True` plus a deliberately narrow second pass
(`parse_data_directories` for just `IMAGE_DIRECTORY_ENTRY_RESOURCE`) —
only what's needed to reach the version-info resource table, not a full
PE parse. A `pefile.PEFormatError` (not actually a valid PE despite the
extension) returns `{"is_pe": False}` rather than an empty dict — a
meaningful negative result, not silence. MSI property extraction is a
known, documented gap: Python 3.13 removed `msilib`, and an MSI is an OLE
compound document requiring a different reader this milestone didn't add
— an `.msi` still routes correctly by extension/true_type, it just won't
have `ProductName`/version evidence.

**Tests**: no dedicated `test_identify_executables.py` in the current
suite — this one's covered indirectly through its use in `route.py`'s
installer-routing tests rather than a standalone extractor test file.

### `identify/audio_video.py`
`mutagen` (`easy=True`, so tag field names are normalized across formats)
for audio; `ffprobe` via `subprocess` for video, entirely optional
(`shutil.which("ffprobe") is None` → empty dict, never an error) since
this milestone doesn't want to require `ffmpeg` as a hard dependency.

**Tests** (`test_identify_audio_video.py`): a WAV's duration, and video
extraction being held gracefully with no `ffprobe` on `PATH` (patched in
the test, not assuming the dev machine's actual `PATH` state).

### `identify/fonts.py`
`fontTools`, `lazy=True` (don't eagerly parse glyph data, only what's
needed) — reads just the `name` table, filtered to four name IDs
(`1`=family, `2`=style, `4`=full name, `16`=typographic family), first
occurrence of each wins. Explicitly closed in `finally`.

**Tests** (`test_identify_fonts.py`): family and style extracted from a
real generated TTF.

### `identify/torrents.py`
A from-scratch bencode decoder (dicts, lists, byte-strings, integers) —
written rather than pulling in a dependency, since the format is small
enough that a ~40-line recursive parser is simpler than a library for
this one use. Reads `info.name` and, if present, counts `info.files` for
a multi-file torrent.

**Tests** (`test_identify_torrents.py`): name extraction, and the
multi-file-torrent file-count path.

### `identify/ml_weights.py`, `identify/wii_wad.py`, `identify/patches.py`, `identify/mame_romdef.py`
Four small, single-purpose extractors that all share the same shape: a
narrow, cheap structural or magic-byte check, not a full parser.
`ml_weights.py` checks that a `.safetensors` file's first 8 bytes decode
as a little-endian length that fits within the actual file size, and byte
9 is `{` — the entire safetensors header format, no library needed.
`wii_wad.py` checks a fixed 4-byte header-size field plus a 2-byte type
tag (`"Is"` or `"ib"`). `patches.py` checks the 5-byte literal `"PATCH"`
magic that is the entire IPS spec. `mame_romdef.py` content-sniffs a
`.rc` file for a `game "..."` line plus `CPU 0x`/`END` markers, since
`.rc` is also an ordinary generic config-file extension used for
unrelated things.

**Tests**: `test_identify_ml_weights.py` (valid structure recognized,
garbage `.safetensors` not claimed), `test_identify_wii_wad.py` (header
recognized, unrelated `.wad` not claimed), `test_identify_patches.py`
(magic recognized, `.ips` without it not claimed),
`test_identify_mame_romdef.py` (content recognized, unrelated `.rc` not
claimed).

### `identify/url_shortcut.py`
Content-sniffed, not just extension — checks the file actually starts
with `[InternetShortcut]` (case-insensitive, leading whitespace
tolerated) before claiming a `.url` file, same reasoning as
`logs.py`/`mame_romdef.py`.

**Tests** (`test_identify_url_shortcut.py`): content recognized, an
unrelated `.url`-named file not claimed.

### `identify/unknown.py`
The guaranteed-last fallback (`priority = 1000`, `can_handle` always
`True`) — a raw 512-byte hex dump plus a printable-ASCII rendering (`.`
for anything non-printable), so even a completely unidentified file gives
the LLM tier *something* concrete to reason from rather than nothing at
all.

**Tests** (`test_identify_unknown.py`): an unrecognized binary falls back
to this, with both preview fields present.

---

## `identify/` — ROM & disc subsystem

This is the deepest part of the codebase; `how-it-works.md` has the
conceptual story. Here's exactly how the four files divide the work.

### `identify/discs.py`
Pure sector-framing math, no filesystem knowledge at all.
`detect_layout()` reads the first 2352 bytes and checks for the 12-byte
CD sync pattern (`00 FF×10 00`); if it's not there, the file is already
"cooked" (plain 2048-byte logical sectors, same as a normal `.iso`) and
`COOKED_LAYOUT` (offset 0, same size) passes through untouched. If the
sync *is* there, byte 15 is the sector's mode — Mode 2 gets an extra
8-byte XA subheader skipped (`MODE2_DATA_OFFSET = 24`), Mode 1 doesn't
(`MODE1_DATA_OFFSET = 16`). `LogicalSectorView` then presents that raw
source as a plain contiguous stream of 2048-byte logical sectors:
`read(n)` for the cooked case is a trivial passthrough; for the raw case,
it walks sector-by-sector (`divmod(pos, LOGICAL_SECTOR_SIZE)`), seeking
into the *raw* stream at each sector's real offset plus the mode-dependent
data offset, so a read spanning a sector boundary correctly skips over
each sector's own sync/address/mode/subheader bytes in between. Works on
any object with `.seek()`/`.read()` — a loose file handle or a zip
member's stream — identically.

**Tests**: no dedicated `test_identify_discs.py`; exercised entirely
through `test_identify_disk_images.py`'s raw-`.bin` cases (which couldn't
pass without this module working correctly) and through
`tests/fixtures/make.py`'s `_wrap_raw_sectors`/`make_raw_cd_bin` helpers
that construct the raw-sector fixtures those tests use.

### `identify/iso9660.py`
A from-scratch minimal ISO9660 (ECMA-119) reader — deliberately not
`pycdlib`, since only two things are ever needed: the volume label, and
the root directory's entry *names* (never full directory tree traversal,
never file contents beyond one specific root-level file read). Takes any
`.seek()`/`.read()` object, same convention as `discs.py` — so the exact
same reader works unmodified on a loose `.iso`, a `LogicalSectorView` over
a raw `.bin`, or a zip member's stream. `_iter_root_records()`'s one real
subtlety: a zero-length directory record means "nothing more in this
sector," not "corrupt data" — ISO9660 directory records never cross a
sector boundary, so a zero hints the reader to skip forward to the start
of the next 2048-byte sector rather than getting stuck. `read_root_file()`
is how `disk_images.py` gets `SYSTEM.CNF`'s actual bytes.

**Tests**: no dedicated test file; exercised through every
`test_identify_disk_images.py` case that reads a real ISO9660 structure
(which is most of them), via `tests/fixtures/make.py`'s
`_build_iso9660_image`/`make_iso9660` fixture builder.

### `identify/disk_images.py`
Ties `discs.py` + `iso9660.py` together into actual console identification,
plus the handful of formats that *aren't* ISO9660 at all:

- **GameCube/Wii**: fixed 4-byte magic at a fixed offset (`0x1C`/`0x18`
  respectively) — no filesystem read needed.
- **WBFS**: checked *before* any ISO9660 attempt, since it wraps sectors
  in its own container rather than exposing a plain ISO9660 filesystem —
  trying the PVD read first would just fail.
- **RVZ** (Dolphin's compressed format): magic-recognized but
  deliberately *not* resolved to a console — it wraps either a GameCube
  or Wii disc, and telling which would mean parsing further into a
  container this milestone doesn't need to open.
- **PS1 vs. PS2**: both have `SYSTEM.CNF` at the ISO9660 root;
  `_ps1_or_ps2()` just checks whether its boot line says `BOOT2` (PS2) or
  plain `BOOT` (PS1), and extracts the serial from the same boot line
  (`dat.normalize_serial()`) in the same pass.
- **PSP**: no `SYSTEM.CNF` check needed — `PSP_GAME`/`UMD_DATA.BIN` as
  root-level entry *names* is enough.
- **Saturn / PC-Engine CD**: no ISO9660 filesystem at all — each format
  has its own fixed boot-sector text signature, scanned across a bounded
  200-sector prefix (`BOOT_MAGIC_SCAN_SECTORS`) rather than assumed at a
  fixed offset, since a rip may or may not have kept the track's 150-
  sector (2-second) pregap.
- **`.bin`'s special treatment**: unlike every other extension in
  `DISC_EXTENSIONS`, a `.bin` that turns out not to be a disc at all
  doesn't become a bare "unknown" — `_not_a_disc()` gives it the same
  512-byte hex preview `UnknownExtractor` would, since most `.bin` files
  genuinely aren't discs and shouldn't lose that evidence to an empty
  claimed-but-unresolved `disk_image` kind.
- **`console_from_disc_stream()`** is the shared entry point
  `archives.py` calls for a disc image sitting inside a zip member — same
  logic as the loose-file path, minus the Nintendo magic-byte checks
  (those need a whole file on disk at fixed absolute offsets in a way
  that doesn't translate to "a stream that happens to be inside a zip").

**Tests** (`test_identify_disk_images.py`, 15 cases): one test per console
path above (generic ISO, PS2-via-BOOT2, PSX-via-BOOT, PSP-via-marker,
GameCube magic, Wii magic, WBFS magic, RVZ-has-no-console,
not-an-iso-at-all), plus the raw-sector-specific cases
(`test_raw_bin_psx_disc_via_system_cnf_boot`,
`test_raw_bin_ps2_disc_via_system_cnf_boot2_mode1`), the boot-magic cases
with and without a pregap (`test_saturn_boot_magic_no_pregap`/
`...with_pregap`, `test_pce_cd_boot_magic`), and the `.bin`-fallback case
(`test_non_disc_bin_falls_back_to_byte_preview`).

### `identify/archives.py`
Member listing without ever extracting, for zip (stdlib `zipfile`), tar
variants (stdlib `tarfile`, matched by filename suffix since
`.tar.gz`/`.tar.bz2`/`.tar.xz` aren't single-suffix extensions `Path.suffix`
would catch), and `.7z` (`py7zr`, added specifically because leaving `.7z`
with no listing at all was causing real false negatives — every `.7z`
archive was landing in `Archives` regardless of content, purely for lack
of a library, not because of any content ambiguity). `.rar` still has no
listing at all (no stdlib support, `rarfile` judged not worth the
dependency for this milestone) — it's still routed by extension alone,
same tier-1 treatment as everything else before a listing exists.
`_sevenz()`'s `except Exception` (broader than `_zip`'s narrow
`zipfile.BadZipFile`) is deliberate: `py7zr` doesn't guarantee one narrow
exception type for malformed input the way `zipfile` does — a fake/corrupt
`.7z` can raise `struct.error`, an `lzma` error, or others, and the
contract here ("anything unparseable yields no member details, never a
crash") has to hold regardless of which one shows up.
`console_from_zip_members()` is the disc-inside-an-archive check — zip
only, deliberately, since `py7zr` has no cheap partial read of a single
member (checking even a few bytes means decompressing the *whole* member
first), a fine cost for a small cartridge ROM but a bad one for a
multi-gigabyte disc dump.

**Tests** (`test_identify_archives.py`): member listing for zip/tar/7z,
a truncated/corrupt zip and a corrupt 7z both held gracefully (empty
dict, not a crash), and `.rar` confirmed to get no listing at all.

### `identify/roms.py`
Covered extensively in `how-it-works.md`. The one thing worth adding here
that isn't in the narrative: **every cartridge ROM gets a CRC32 computed
unconditionally**, streamed in 1MB chunks (`_crc32_of`), regardless of
whether the header check for that extension succeeded — an unverified
SNES/NDS file still gets a `crc32` field, so a DAT lookup can still run
for it even though there was no header to check in the first place. The
CRC32 is purely a cartridge-title lookup key (`dat.lookup_title_by_crc`),
never dump verification.

**Tests** (`test_identify_roms.py`): one test per header-verified console
(NES, GBA, all three N64 byte orders, Genesis, the GB-vs-GBC CGB-flag
disambiguation), the mislabeled-extension negative case, the SNES/NDS
extension-only pair, `.dol`-as-wii, both FDS signature variants plus the
unsigned negative case, and `test_crc32_is_computed_from_full_file_contents`
pinning the CRC32 computation itself against a hand-computed reference
value.

---

## `llm/` — the LLM tier

### `llm/schema.py`
One JSON Schema (`RESPONSE_JSON_SCHEMA`) shared verbatim between Ollama's
schema-constrained `format` field and Lemonade's OpenAI-compatible
`response_format` — same schema, two different request envelopes around
it, so there's exactly one place to update if the contract ever changes.
`LlmVerdict` is the pydantic model every parsed reply gets validated
against; `suggest_delete` defaults `False` so an older or looser model
that omits the field entirely still parses.

**Tests**: no dedicated test file — exercised entirely through
`llm_backend.py`'s parsing tests, since the schema only has meaning in
the context of an actual reply being validated against it.

### `llm/prompts.py`
`build_system_prompt()` assembles the folder allowlist (sorted, so prompt
text is deterministic across runs — not load-bearing for correctness, but
makes any diff between two prompt renders meaningful rather than noise
from set-ordering) plus, when there's history, a rendered block of recent
accepted examples (`_render_examples` — evidence JSON, then the verdict
that was kept, one per line). `build_user_message()` is just the evidence
bundle's relevant fields as JSON — no editorializing, no reformatting.
`PROMPT_VERSION` is a plain string constant bumped by hand whenever the
template text changes meaningfully, recorded on every routing-log entry
so `eval`/analysis can tell which prompt version produced which verdict.

**Tests** (`test_llm_prompts.py`): the allowlist appears in the system
prompt, no examples section renders when there's no history, examples
render correctly when there is history, and the user message is exactly
the evidence as JSON.

### `llm/backend.py`
Two `Backend` implementations behind one `Protocol`
(`OllamaBackend`/`OpenAICompatBackend`), both doing a single JSON POST via
stdlib `urllib` — deliberately no HTTP client dependency for something
this simple. `OllamaBackend` uses the *native* `/api/chat` rather than
Ollama's own OpenAI-compatible endpoint specifically because the native
one exposes things the compat layer doesn't: `format` (full JSON-schema
constraint, not just "valid JSON"), `options.num_ctx` (Ollama's default
context is too small for an evidence bundle), `keep_alive` (a short value
like `"2m"` frees VRAM soon after a run, so a model doesn't sit loaded
competing for GPU memory with, say, a game), and `think: false`
(suppresses a reasoning model's internal monologue from polluting the
response). Every failure mode funnels through `LlmError`: HTTP error
status, unreachable/timeout, non-JSON response body, an unexpected
response *shape* (missing the key the code expects to find the content
at), invalid JSON in the model's own reply content, or that content
failing `LlmVerdict` schema validation. `_parse_verdict()` strips
`<think>...</think>` blocks via regex *before* attempting JSON parsing —
belt-and-suspenders alongside the Ollama-side `think: false`, since a
reasoning model (or Lemonade, which has no `think` parameter at all) might
emit one anyway. `describe_backend()` (for `doctor`) does genuinely
different reachability checks per backend: Ollama gets `/api/tags` (is
the configured model actually pulled?) plus `/api/show` (does it report
vision capability?); Lemonade gets `/models` only, since Lemonade has no
equivalent vision-capability introspection endpoint in this contract.

**Tests** (`test_llm_backend.py`, 11 cases): a valid reply parsed for both
backends, `<think>` blocks stripped, and one test per `LlmError` trigger
(invalid JSON, schema mismatch, HTTP error, unreachable, timeout, an
unexpected response shape), plus `backend_for()`'s dispatch-on-config and
both `describe_backend()` outcomes (reachable-and-found,
not-reachable-at-all) — all against `fake_llm_server.py`, never a real
model.

### `llm/__init__.py`
Pure re-export (`Backend`, `LlmError`, `LlmVerdict`, `backend_for`,
`describe_backend`) — `route.resolve()` is documented as the only caller
outside this package, so this file exists purely to give that one caller
a stable, minimal import surface rather than reaching into `backend.py`/
`schema.py` directly.

---

## `dat.py`

Technically not under `identify/`, but tightly coupled to the ROM/disc
subsystem — covered in depth in `how-it-works.md` and ADRs 0007/0008.
Two independent parsers for two differently-shaped libretro DAT text
formats (serial-keyed for PS1/PS2/PSP, CRC32-keyed for cartridge
consoles), both built on the same `_matching_paren_end()` bracket-counting
helper to correctly extract one `game ( ... )` block's text even when it
contains nested parenthesized sub-blocks (`rom ( ... )`), and both cached
per-file via `functools.cache` on `_load_dat`/`_load_crc_dat` so a DAT
file (potentially tens of thousands of entries) is only ever parsed once
per process, not once per lookup.

**Tests** (`test_dat.py`): serial normalization both directions
(DAT-style `SLUS-20267`, `SYSTEM.CNF`-style `SLUS_202.67`), the no-match
case, correct extraction of the *outer* `name`/`serial` fields and not a
nested `rom ( ... )` block's own copies of those same field names, and the
full lookup path (match, wrong console configured, unknown serial) — then
the identical shape of tests again for the CRC32-keyed parser (extraction,
case-insensitive lookup, wrong console, unknown CRC).
