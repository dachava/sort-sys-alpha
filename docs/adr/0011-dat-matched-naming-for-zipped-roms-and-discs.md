# ADR 0011: DAT-matched naming for zipped ROMs and discs

## Status
Accepted. Extends ADR 0007/0008 to the one case both explicitly scoped out.

## Context
ADR 0007 (serial-keyed PS1/PS2/PSP) and ADR 0008 (CRC32-keyed cartridge
consoles) both only apply a DAT-matched title to a *loose* file. A zipped
ROM or disc already gets console *detection* (`single_console_from_members`
for cartridge extensions, `console_from_zip_members` for a disc image
inside the archive), but the archive keeps its own filename regardless of
whether a DAT match would exist for what's inside it.

The user's own real usage pattern made this worth closing: ROM zips in
practice are either a single game, or a multi-file set of the *same*
game (a multi-track disc dump bundled with its `.cue`) -- not, as the
"legitimate multi-game zip" case worried about, an arbitrary mixed
collection. That narrows the ambiguity concern considerably: a title only
needs assigning to the archive as a whole when there's genuinely one game
in it, which is the common case, not the exception.

## Decision
- **Cartridge zips: strict single-member only.** A new function,
  `single_rom_member()`, returns the one archive member with a recognized
  ROM extension only when there is *exactly* one such member in the whole
  listing -- stricter than `single_console_from_members` (which still
  allows several same-console members for routing purposes, e.g. a
  legitimate multi-game collection). Only when exactly one member exists
  does a CRC32 get computed (`member_crc32()`, reading the member's full
  decompressed content, zip or 7z, no extraction to disk) and looked up.
  A multi-ROM zip keeps today's filename-based naming -- correct routing,
  no attempt at a single title for content that isn't single.
- **Disc zips: serial from whichever member has it.** `console_from_disc_
  stream()` and `console_from_zip_members()` both now return `(console,
  serial)` instead of just `console`. This needs no extra restriction the
  way the cartridge case does: a multi-track dump of *one* disc naturally
  has only one member with the ISO9660 filesystem carrying `SYSTEM.CNF`
  (other tracks are raw audio/data with no filesystem at all, so they
  simply don't contribute a console or serial) -- there's structurally
  only ever one serial to find, not several to choose between.
- **MSX stays out of scope here.** Its zip-member match
  (`msx_console_from_archive`) is already a weaker, name-corroborated
  signal (ADR from the MSX work), and extending DAT naming to it is a
  separate decision, not bundled into this one.
- **Integration point is still `name_hint`, not routing**, same principle
  as ADR 0007/0008: a DAT hit only replaces what `naming.py` turns into
  the final filename. The archive's category (`ROMs/<console>` vs.
  `Archives`) is decided exactly as before.

## Consequences
- `identify/disk_images.py`'s `console_from_disc_stream()` return type
  changes from `str | None` to `tuple[str, str | None] | None`.
- `identify/archives.py`'s `console_from_zip_members()` return type
  changes from `str | None` to `tuple[str | None, str | None]` (console,
  serial) to match.
- `route.py`'s `kind == "archive"` branch now computes a `name_hint` for
  both the cartridge-CRC32 and disc-serial paths, mirroring the loose-file
  branches' DAT lookups exactly.
- A genuinely mixed-game zip (several different games, not tracks of one)
  still gets no DAT-matched name -- correctly, since there's no single
  title to assign a whole archive full of unrelated games.
