# ADR 0008: Cartridge ROM DAT matching by CRC32

## Status
Accepted. Extends M7 alongside ADR 0007.

## Context
ADR 0007 covered PS1/PS2/PSP discs, matched by serial number straight out of
`SYSTEM.CNF`. The user also wanted the same treatment for SNES, and asked
whether the rest of the libretro-database "developer" DATs (NES, Genesis,
GBA, N64, GB/GBC, Game Gear, 32X, SG-1000, Master System) would work the same
way. They don't -- these are cartridge dumps, not discs, and the libretro
DAT for each one turns out to be a different shape again: ClrMamePro text
like the PS1/PS2 DAT, but keyed by **CRC32 of the whole ROM file**, with no
serial field at all. Title lives in a `comment` field instead of `name`:

```
game (
    comment "3 Ninjas Kick Back (USA)"
    developer "Malibu Games"
    rom ( crc F2EE11F9 )
)
```

Unlike the PS1/PS2 serial (already sitting in a boot-sector string), a
cartridge ROM has no equivalent cheap identifier -- the only way to get the
matching key is to hash the file's own bytes. Cartridge ROMs are small
(single-digit to low tens of MB), so hashing the full file at rules-tier is
cheap; this isn't the byte-for-byte verification a real No-Intro/Redump
check would be, it only establishes a title, same as ADR 0007's serial
lookup.

Checked against several consoles in the actual libretro-database repo
(`metadat/developer/`): NES, SNES, GB, GBA, N64, Genesis, Game Gear, 32X,
SG-1000, and Master System all share this exact shape. Dreamcast does not --
it's disc-based with a `serial` field but no outer title (titles sit on
per-track nested `rom (name "...")` entries instead) -- out of scope here.

## Decision
- **`dat.py` gains a second parser**, `parse_crc_dat(text)`, returning
  `{CRC32_HEX: title}` from every `game ( ... )` block's `comment` field and
  its nested `rom ( crc ... )` value. Separate from `parse_dat` (ADR 0007's
  serial parser) since the field names and matching key are both different;
  no attempt to unify the two into one schema-sniffing parser.
- **`identify/roms.py`'s `RomExtractor.extract()` now computes a CRC32 of
  the full file** (streamed, not loaded whole into memory) for every
  cartridge extension it handles, stored as `details["crc32"]` alongside
  the existing `console`/`verified` fields.
- **Same `roms.dat_files` config map as ADR 0007** -- `{console: path}` --
  reused as-is. Which lookup function runs (`lookup_title` vs
  `lookup_title_by_crc`) is decided by the evidence's `kind`
  (`disk_image` vs `rom`) in `route.py`, not by anything in config. A
  console with no entry keeps today's behavior (filename stem as the name).
- **Integration point is still `name_hint`, not routing** -- same as ADR
  0007, the console/folder decision is unchanged; a DAT hit only replaces
  what `naming.py` slugifies into the final filename.

## Consequences
- `roms.py`'s extractor now always does one full-file read (for the CRC32)
  even when the header check alone would have been enough -- acceptable
  given cartridge ROM sizes, but would need revisiting if this extractor
  ever had to handle genuinely large files.
- `route.py`'s `kind == "rom"` branch now carries a DAT lookup the same
  shape as the `kind == "disk_image"` branch, but calling a different
  function (`lookup_title_by_crc`) against a different parsed shape.
- This still only yields a *title*, not dump verification -- a real
  No-Intro/Redump check (confirming the dump is a known-good, unmodified
  copy, not just "a ROM with this title exists") remains separate,
  not-yet-built scope, as ADR 0007 already noted.
- Dreamcast (and any other disc-with-no-clean-outer-title DAT shape) is
  explicitly not covered by either ADR 0007 or this one.
