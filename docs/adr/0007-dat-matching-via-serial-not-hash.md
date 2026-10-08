# ADR 0007: PS1/PS2/PSP DAT matching by serial, not content hash

## Status
Accepted. Starts M7; amends PLAN.md section 4.9's "later milestone" note.

## Context
PLAN.md originally described M7 as "exact identification by hashing
(CRC32/SHA1) against No-Intro/Redump DAT files" -- the standard approach
for cartridge ROMs and disc dumps, verifying byte-for-byte against a known
database. The user's actual DAT file (libretro's "Data Center" project,
e.g. `psxdatacenter` for PS1/PS2/PSP) turned out to be a different shape
entirely: ClrMamePro's paren-delimited text format, not Logiqx XML, and
critically -- no CRC32/MD5/SHA1 fields at all. Each `game ( ... )` block
carries a `serial` (e.g. `SLUS-20267`) and a `name` (the canonical title),
plus metadata (developer, publisher, genre, release date, description)
useful for naming but not needed for matching.

This is good news for scope: a PS1/PS2/PSP disc's serial is already sitting
in `SYSTEM.CNF`'s boot line (`BOOT2 = cdrom0:\SLUS_202.67;1`), which
`identify/disk_images.py` already reads to tell PS1 apart from PS2. No
hashing, no reading the whole disc image, no new large-file I/O -- just a
few extra bytes already in hand, normalized and looked up.

## Decision
- **New module `dat.py`**, scoped to this exact format: `parse_dat(text)`
  returns `{normalized_serial: title}` for every top-level `game ( ... )`
  block, matching the *first* `name`/`serial` pair in each block (the
  game-level fields, which always precede the nested `rom ( ... )` block's
  own `name`/`serial` in this format -- so a plain first-match search is
  correct without a full recursive parser).
- **Serial normalization is the matching key.** `SLUS_202.67` (SYSTEM.CNF's
  style) and `SLUS-20267` (the DAT's own style) both normalize to
  `SLUS-20267`, so either side of a lookup compares correctly regardless
  of which convention it came from.
- **Config:** `[roms.dat_files]` maps console name -> local DAT path (e.g.
  `ps2 = "~/dat/ps2.dat"`). A console with no entry just keeps today's
  behavior (ISO volume label as the name hint) -- this is additive, not a
  breaking change to existing configs.
- **Integration point is `name_hint`, not routing.** The console (and
  therefore the `ROMs/<console>` folder) is already decided by the
  existing header/SYSTEM.CNF detection; a DAT match only replaces the name
  hint `naming.py` slugifies into the final filename. No category logic
  changes.
- **Scope: loose PS1/PS2 discs only.** Zipped discs got console detection
  without DAT-matched naming here; naming for a zipped disc was added
  later, see ADR 0011.
- **Not a replacement for hash-based matching.** This only verifies "a
  disc with this serial is canonically called X" -- it says nothing about
  whether the dump is a known-good, unmodified copy. A real
  No-Intro/Redump CRC32/SHA1 DAT (for cartridge ROMs, and for verifying
  disc dumps byte-for-byte) is separate, not-yet-built scope with a
  different parser (Logiqx XML) and a different matching key entirely.

## Consequences
- `identify/disk_images.py`'s `_ps1_or_ps2` now returns `(console, serial)`
  instead of just `console`; `console_from_disc_stream` (the zip-member
  path) originally unpacked and discarded the serial, until ADR 0011 wired
  it through for zipped-disc naming too.
- `route.py`'s `kind == "disk_image"` branch calls `dat.lookup_title()`
  when a serial was read, preferring a DAT match over the volume label.
- If a later milestone adds genuine hash-keyed DAT support (cartridge
  ROMs, arcade sets, or disc-dump verification), that's new scope against
  a different file format and a different key -- this ADR's parser and
  matching logic don't generalize to it as-is.
