# How sort-sys-alpha works

This is the narrative reference: what the tool is, why it's built the way
it is, how each piece works, and the real bugs that shaped it. `PLAN.md` is
the spec and `CLAUDE.md` is the contributor contract; this doc is the story
in between — written to be useful as personal reference now and as raw
material for a blog post later.

## The problem

A Windows `Downloads` folder accumulates everything: installers, PDFs,
screenshots, ROM dumps, archives, logs, random `.bin`/`.iso` files nobody
remembers downloading. The usual answer is either "sort it by hand" (never
happens) or "hand it to a cloud service that reads your files" (no). The
premise here, inspired by an XDA piece about putting a local model in
charge of naming and filing downloads: run a small LLM entirely on your own
GPU, but don't actually trust it with the decisions that matter. Let
deterministic rules handle everything they can settle by extension, magic
bytes, or header signature — which turns out to be nearly everything — and
reserve the model for naming cryptic files and the genuinely ambiguous
cases rules can't resolve.

## Core philosophy

Seven hard rules, enforced in code, not in a prompt:

1. **Rules before the model.** Anything a byte signature can settle never
   reaches the LLM. The model is the slow, untrusted fallback, not the
   router.
2. **Local only.** The model server runs on loopback on the same machine.
   `config.py` refuses a non-loopback endpoint unless an explicit
   `allow_remote` override is set. File contents never leave the box.
3. **Plan, then apply.** Two separate commands. `plan` only ever writes
   `plan.json`/`report.md`; nothing in `source` is touched until `apply`
   runs, deliberately, against that plan.
4. **The confidence gate lives in code.** A model's own claimed confidence
   is irrelevant if `gate.py`'s independent checks don't also pass — the
   folder allowlist, name safety, a stat/hash-unchanged check between plan
   and apply, depth/size limits, "hold the whole group if any member
   fails." A prompt change can never be the only thing standing between a
   bad verdict and a real move.
5. **Never delete.** The model may *suggest* deletion; nothing acts on that
   automatically. The only files removed are the source side of a verified
   move, and — the one explicit, scoped exception — the manual `prune`
   command, which only ever removes folders with zero files at any depth
   (ADR 0006).
6. **Every move is journaled before it executes**, so `undo` is always
   possible.
7. **A schedule mode doesn't change the gate.** `auto` mode lets a
   scheduled `run` call `apply` automatically; `plan` mode stops after the
   plan and waits for a human. Either way, the exact same gate decides what
   actually moves (ADR 0003).

## The pipeline

```
scan → identify → route (rules | LLM) → gate → plan.json / report.md → apply → journal
```

**Scan** walks `source` (default `~/Downloads`), skipping partial downloads,
anything younger than `min_age_minutes`, locked files, and its own state
folder. Subfolders get their own classification pass (below) before their
contents ever reach the main per-item loop.

**Identify** builds an evidence bundle for each item — cheap, deterministic
facts, no model involved yet: true file type from magic bytes, size/dates,
Zone.Identifier download source, and format-specific metadata (EXIF, PE
version info, PDF text, ISO volume label, ROM header fields, archive member
listing, and so on). Each file type is a small plugin
(`identify/<type>.py`) exposing `can_handle(evidence)` and
`extract(path) -> dict`; adding a new type never touches the dispatch
logic, just adds one module and a fixture.

**Route** is two tiers. Tier 1 (`route.py`'s rules) matches on true type,
extension, header signature, or download source, and settles the large
majority of files — images, audio, PDFs, notes, logs, installers, ISOs, and
every ROM/disc whose console a signature can confirm. A rule-tier verdict
always carries confidence 1.0; it's deterministic or it doesn't happen.
Tier 2 is the LLM, reached only when no rule applies — an unfamiliar
extension, a genuinely ambiguous disc image, or just naming a cryptically
named file. The model only ever picks from a fixed folder allowlist and
returns a schema-validated verdict; it cannot invent a destination.

**Gate** (`gate.py`) is the safety floor described above, independent of
which tier produced the verdict. It computes the real target path, checks
it against the allowlist, checks the name is safe, and — since a recent
addition — checks whether the exact same content is already sitting in
that target folder from an earlier run (more on that below). Anything that
fails any check is **held**: left exactly where it is, with the reason
recorded, never touched further.

**Plan** writes `plan.json` (machine-readable, hand-editable before apply)
and `report.md` (human-readable: every move and every hold with its
reason). Nothing in `source` changes yet.

**Apply** executes that plan: same-volume files are renamed in place;
cross-volume moves copy, verify the hash, then remove the source — the only
"delete" anywhere in the system, and it's one half of a verified move.
Every move is written to `journal.jsonl` *before* it runs, so `undo <run>`
can always put things back.

## Subfolders: unit, grab-bag, or unsure

Every subfolder of `Downloads` gets classified before its contents are
considered individually:

- **Unit** — the whole folder moves intact, structure untouched. Signals:
  an extracted app (`.exe` + its `.dll`s, or a literal `setup.exe`), a
  disc/game dump, an album (audio + a `.cue`/cover), a code project
  (`.git`, `package.json`, `pyproject.toml`), a folder of nothing but one
  file type, or a folder of nothing but helper scripts for a tool that
  lives elsewhere.
- **Grab-bag** — mixed, unrelated files with no project/app markers; each
  member is sorted individually, same as a top-level file.
- **Unsure** — conflicting or insufficient signals; the whole folder is
  held, nothing inside moves.

Real usage surfaced sharper edges here than the simple three-way split
suggests. A portable tool's folder got split instead of moved intact,
because "extracted app" and "disc dump" markers could both apply to the
same folder and the classifier picked the wrong one — fixed by making a
confirmed disc identification win outright over weaker markers. A helper
script (`chd2cue.bat`) sat alone in its own folder with no `.exe` anywhere
in that tree, and "a folder of nothing but a lone script" wasn't
recognized as a coherent unit at all — fixed by adding a dedicated
script-only-folder signal, so it moves with its tool instead of getting
split off into whatever category a bare `.bat` file would otherwise land
in.

## ROMs and discs: the deepest rabbit hole

This is where "rules before the model" gets tested hardest, because a
console's identity usually isn't in the file extension at all.

**Cartridge consoles** get a real header check wherever one exists: NES's
`NES\x1a` magic, Game Boy/Color's Nintendo logo bytes (plus a CGB flag to
tell GB from GBC), GBA's fixed entry-point bytes, N64's three different
byte-order magics depending on dump format, Genesis/Mega Drive's `SEGA`
string at a fixed offset, and the Famicom Disk System's two possible
signatures (a headered fwNES-style dump, or a bare disk image starting
directly with its own block marker). SNES, NDS, and Wii homebrew have no
cheap fixed-offset signature to check, so those stay extension-only — a
documented, deliberate trust level, not a gap nobody noticed.

**Discs** are identified from their filesystem, not a header offset:
`disk_images.py` reads the ISO9660 volume descriptor, and for PS1/PS2/PSP
specifically reads `SYSTEM.CNF`'s boot line to tell which PlayStation
generation it is — and, as of a later addition, to read the disc's serial
number straight out of that same line. Saturn and PC-Engine CD/TurboGrafx
discs are identified by a boot-sector text signature scanned across a
bounded window of sectors (handling discs that may or may not include
their pregap). Raw `.bin` CD dumps need their own sector-framing logic
first — 2352-byte raw sectors have to be unwrapped to the 2048-byte
logical sectors ISO9660 actually expects before any of the above can run
at all, whether the dump is Mode 1 or Mode 2 Form 1.

**Archives** get the same treatment without ever extracting anything:
`.zip` (and, later, `.7z` via `py7zr`) member listings are read directly,
and if every ROM-extension member in that listing belongs to one console,
the whole archive routes to that console's folder, still zipped. The same
listing is also used to peek inside for a disc image (a zipped `.bin`/`.iso`)
and run the same disc-signature check against that member's stream, no
extraction to disk — though this specific check stays zip-only, since
`.7z` has no equivalent cheap partial read; checking even a few bytes of a
solid-compressed 7z member means decompressing that whole member first,
which is fine for a small ROM file but a bad trade for a multi-gigabyte
disc dump.

MSX needed its own carve-out: MSX cartridge dumps use the generic `.rom`
extension, which is far too ambiguous to trust blindly (lots of unrelated
things are named `*.rom`). The fix corroborates it with a second, cheap
signal — the archive's own filename also has to say "MSX" — rather than
either trusting the extension everywhere or refusing to support it at all.

**DAT matching** (libretro's "Data Center" and "libretro-database"
projects) upgrades a correctly-identified ROM from a bare volume label or
filename to its real title, using two different keys depending on shape:
PS1/PS2/PSP discs are matched by the serial already read from
`SYSTEM.CNF` against a serial-keyed DAT; cartridge consoles (NES, SNES,
Genesis, GBA, N64, GB/GBC, FDS, Game Gear, Master System, 32X, SG-1000,
and more as DAT files get added) are matched by a CRC32 of the whole ROM
file against a differently-shaped, hash-keyed DAT. The same matching
reaches inside a zip/7z too, but only when the archive contains exactly
one identifiable game — a strictly single-member check for cartridge
zips (stricter than the console-detection check, which still allows
several same-console members for a legitimate multi-game collection), and
naturally single for a disc zip since a multi-track dump of one disc only
ever has one member with the filesystem carrying the serial. Neither
shape is byte-for-byte dump *verification* against No-Intro/Redump —
that's a real, separate, not-yet-built thing — these only establish "a
ROM/disc with this serial or hash is canonically called X."

### The bugs that taught the lesson

A few real false positives, found only by running the tool against an
actual Downloads folder rather than synthetic fixtures, are worth keeping
as concrete illustrations of why the rules tier has to *verify*, not just
pattern-match on extension:

- **`.md` is both Markdown and a legitimate Genesis cartridge extension.**
  A plain Markdown note was silently sent to the LLM tier carrying
  misleading "this might be a Genesis ROM" evidence, purely because the
  extractor that claims `.md` first happens to be the ROM one. The fix:
  an unverified Genesis guess on a note-like extension falls back to being
  treated as a note, not a maybe-ROM.
- **The same collision, one layer up.** A GitHub "Download ZIP" export —
  a developer utility's source code, not a ROM at all — landed in
  `ROMs/genesis` purely because its only recognizable-extension member was
  a `README.md`. Trusting `.md` as a ROM signal *inside an archive* had
  the identical flaw as trusting it for a loose file; the fix was the same
  idea applied one level deeper — require an actual verified Genesis
  header inside that `.md` member before trusting it, not just the
  extension.
- **A portable tool's executable and its own helper script got filed to
  two different places** because they weren't even in the same folder to
  begin with — the `.exe` was a sibling loose file elsewhere in
  `Downloads`, and its script-only subfolder had no unit signal strong
  enough to move it anywhere coherent on its own.

None of these needed the model to get smarter. Each one was a rules-tier
gap — a signal being trusted further than it actually proved anything —
and each fix made the deterministic tier a little more honest about what
it actually knows versus what it's only guessing from an extension.

## Duplicates: never silently pile up

Two related checks, both strictly "never delete, just hold and report":

- **Within one scan batch** (ADR 0005): if two freshly-scanned files in
  `source` turn out to be byte-identical, only one proceeds through the
  pipeline; the other is held immediately, before even reaching
  identify/route, with the reason naming which file it duplicates. This
  existed because real usage showed the same `readme.txt`/license/installer
  repeated dozens of times across unrelated downloads — one measured run
  had 74 files across 16 duplicate groups, about 58 of which would
  otherwise have landed as ugly `-2`/`-3`/... siblings of a file already
  filed.
- **Against what's already filed** (ADR 0009): the same content-equality
  check, but run at gate time against the files already sitting in a
  move's *computed target folder* — so redownloading something you
  already have correctly filed doesn't quietly become a second,
  byte-identical copy under a different name. `movefs.unique_target()`
  (the function that actually resolves a move's final path) only ever
  checked for a *name* collision, with no concept of content equality at
  all, so this was a real, measurable gap until this check closed it.

Both lean on the same cost trick: size is free (already stat'd), so it
narrows the candidate set before anything is actually hashed with SHA-256
— hashing only ever runs on files that already share a size with some
candidate, not on everything in sight.

## The feedback loop ("it learns" without fine-tuning)

Three pieces, all data-driven rather than training-driven:

1. **Few-shot from history** — recent accepted, non-undone LLM verdicts
   get shown back to the model as examples in future prompts.
2. **Corrections** — a hand-edit to `plan.json` before `apply`, or a later
   `undo`, is logged as a correction/negative example.
3. **An eval set** — a folder of labeled synthetic fixtures with expected
   categories, scored with `eval` to compare models, context sizes, and
   prompt versions with actual numbers instead of vibes.

`routing.jsonl` is the record every one of these reads from: every verdict
the LLM tier ever produced, with its evidence summary, prompt version,
confidence, and outcome. Rule-tier verdicts don't get logged here — they're
deterministic by construction, so there's nothing for the model to learn
from them.

## Re-triaging already-filed content

Detection gets better over time (a new DAT file, a newly-supported
console, a fixed false positive), which raises an obvious question: what
about everything that already got filed — or misfiled — under the old
rules? Two commands answer two different versions of that question.

`--source` answers "should this have gone somewhere else." It overrides
`config.toml`'s `source` for one run only, so `plan --source
Downloads\_Filed\Archives` re-triages an already-filed folder against
today's rules, using the exact same `dest`, DAT files, and allowlist as a
normal run. The override's own folder name labels the output
(`report-Archives.md` instead of `report.md`) so a rescan never clobbers
the normal run's report, and the duplicate-against-destination check above
means anything that would've been a re-file doesn't just pile up as a
redundant copy next to where it already correctly landed.

`rename` answers the narrower "same folder, better name" question — for
when a naming convention changed (ADR 0010) or a new DAT match exists for
something that's already correctly filed, and recategorizing was never
the question. It re-runs identify/route fresh on every already-filed
file and recomputes its name, but *never* moves it to a different
category: a fresh verdict that disagrees with the file's current folder
gets held with an explicit "use `--source` instead" reason rather than
acted on. It reuses the exact same `gate_item()` safety checks a normal
plan does (ADR 0012).

One real bug only showed up when actually running the `--source` rescan
for real: the duplicate-against-destination check didn't exclude a
candidate's own path from its search, so re-triaging a folder *already
inside* `dest` made a file match itself and get held as "an exact
duplicate of itself." Fixed by excluding the candidate's own path from
the comparison — a small reminder that "scan a folder that's also the
destination" is a genuinely different case from "scan `source`, file into
`dest`," even though both reuse the identical duplicate-check code.

## Windows integration

Developed entirely on Linux, deployed on Windows 11 — every Windows-only
behavior sits behind a small adapter with a Linux no-op/fake
implementation, so the whole suite runs in CI on both `ubuntu-latest` and
`windows-latest` without ever needing a real Windows box for tests:
Zone.Identifier alternate-data-stream reading (download source metadata),
file-lock detection, and the Scheduled Task registration script. The
scheduled `run` command picks `auto` (plan + apply through the same gates,
no human in the loop) or `plan` (stop after planning, notify, wait for a
manual `apply`) from config — and either way, the gate itself never bends;
the schedule mode only decides whether `apply` gets called automatically,
not what's allowed to move.

## CLI reference

```
sort-sys-alpha scan [--source DIR]  # inventory + evidence only, no model
sort-sys-alpha plan [--source DIR]  # produce plan.json + report.md
sort-sys-alpha apply [--plan FILE]  # execute a plan
sort-sys-alpha run [--source DIR]   # plan + apply with gates (scheduler entry point)
sort-sys-alpha undo [RUN_ID|last]   # revert a run via the move journal
sort-sys-alpha eval                 # score the labeled fixture set
sort-sys-alpha doctor               # check model server, config, permissions
sort-sys-alpha prune                # remove empty folders under source, recursively
sort-sys-alpha rename [--path DIR]  # recompute names for already-filed files, never recategorizes
```

`--config` overrides the config file path on every command; `--source`
overrides just the source folder for one run, labeling its output so it
never collides with a normal run's report.

## Where it stands

| Milestone | What it covers | Status |
|---|---|---|
| M0 | Repo skeleton, CI matrix, config loading | done |
| M1 | Scan + identify, file groups, ROM/disc header detection | done |
| M2 | Rules tier, plan/apply/undo/journal, subfolder classification | done |
| M3 | LLM tier (Ollama + Lemonade), gate, reports | done |
| M4 | Windows integration, Scheduled Task, auto/plan modes, notifications | done |
| M5 | Feedback loop + eval | done |
| M6 | Vision (images, scanned PDFs) | explicitly deprioritized — routing is format-based, not content-based, so vision doesn't change any decision this tool makes |
| M7 | ROM DAT matching | PS1/PS2/PSP serial matching, cartridge CRC32 matching (12 consoles now), and single-item zip/7z naming all done; arcade sets and byte-for-byte dump verification against No-Intro/Redump remain open |
| M8 | Per-category naming templates | `{title}` default (ADR 0010) and the `rename` command (ADR 0012) both done; per-category overrides and full field extraction still open |

Also still open, called out explicitly rather than silently assumed: dedup
stays loose-file-only (a duplicate whole folder, or a duplicate hiding
inside two different archives, isn't detected); `.7z` disc-in-archive
detection isn't implemented for the cost reasons above; a genuinely
mixed-game zip still gets no DAT-matched name, correctly, since there's no
single title to assign a whole archive of unrelated games; and a few
cartridge consoles with no header signature (SNES, NDS, Wii homebrew,
SG-1000) stay extension-only by design, not by oversight.

## Decision record index

Every non-obvious design call lives in `docs/adr/`, numbered in the order
it was made:

- **0001** — Python core, with a thin PowerShell layer only for Windows-only
  plumbing (Scheduled Task, ADS).
- **0002** — Destination layout (`Downloads\_Filed\<Category>`).
- **0003** — Scheduled-run mode (`auto`/`plan`) is configurable; supersedes
  part of 0002.
- **0004** — Feedback loop design: what `routing.jsonl` records, how
  few-shot examples and corrections are selected.
- **0005** — Exact-content duplicate detection within one scan batch.
- **0006** — The `prune` command: the one explicit, scoped exception to
  "never delete."
- **0007** — PS1/PS2/PSP DAT matching by serial number, not a content hash.
- **0008** — Cartridge ROM DAT matching by CRC32, a different DAT shape
  from 0007's.
- **0009** — Extending 0005's duplicate detection to also check against
  what's already filed, not just the current scan batch.
- **0010** — `{title}` (human-readable, no date prefix) replaces
  `{date}_{slug}` as the naming default for every category.
- **0011** — Extending 0007/0008's DAT matching to a single-item zip/7z,
  not just a loose file.
- **0012** — The `rename` command: recomputes names for already-filed
  files, never recategorizes.
