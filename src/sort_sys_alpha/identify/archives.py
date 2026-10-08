"""Archive member listing, via stdlib `zipfile`/`tarfile` plus `py7zr` for
`.7z`. Never extracts to disk. See PLAN.md section 4.3.

`.rar` still can't get a member listing (no stdlib support, and rarfile is
an extra dependency this milestone doesn't need), so it's still routed
deterministically by extension alone (PLAN.md rule 1: rules before the
model), same as every archive type before a listing is read.

`.7z` disc-in-archive detection (the zip-member equivalent in
`console_from_zip_members` below) is deliberately NOT implemented: py7zr has
no cheap partial-read of a single member the way `zipfile.ZipFile.open()`
does -- extracting even the first few KB of a solid-compressed 7z member
means decompressing that whole member into memory first. For a multi-GB
disc dump, that's a real cost this identification step shouldn't pay. A 7z
containing a disc image still gets a member listing, but no console
detection from the disc's own header -- it falls through to `Archives`
unless `single_console_from_members` already matched on cartridge
extensions alone.
"""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path
from typing import Any

import py7zr

from .base import Extractor
from .disk_images import DISC_EXTENSIONS_IN_ARCHIVE, console_from_disc_stream
from .types import Evidence

MAX_MEMBERS = 20

ZIP_EXTENSIONS = {".zip"}
TAR_EXTENSIONS = {".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz"}
RAR_EXTENSIONS = {".rar"}
SEVENZ_EXTENSIONS = {".7z"}
NO_LISTING_EXTENSIONS = RAR_EXTENSIONS


class ArchiveExtractor(Extractor):
    name = "archive"
    priority = 45

    def can_handle(self, evidence: Evidence) -> bool:
        return (
            evidence.extension in ZIP_EXTENSIONS
            or evidence.extension in SEVENZ_EXTENSIONS
            or evidence.extension in NO_LISTING_EXTENSIONS
            or any(evidence.original_name.lower().endswith(suffix) for suffix in TAR_EXTENSIONS)
        )

    def extract(self, path: Path, evidence: Evidence) -> dict[str, Any]:
        if evidence.extension in ZIP_EXTENSIONS:
            return self._zip(path)
        if evidence.extension in SEVENZ_EXTENSIONS:
            return self._sevenz(path)
        if evidence.extension in NO_LISTING_EXTENSIONS:
            return {}
        return self._tar(path)

    def _zip(self, path: Path) -> dict[str, Any]:
        try:
            with zipfile.ZipFile(path) as zf:
                infos = zf.infolist()
                names = [i.filename for i in infos[:MAX_MEMBERS]]
                total_size = sum(i.file_size for i in infos)
        except (zipfile.BadZipFile, OSError):
            return {}
        return {"member_count": len(infos), "members": names, "uncompressed_size": total_size}

    def _sevenz(self, path: Path) -> dict[str, Any]:
        try:
            with py7zr.SevenZipFile(path, mode="r") as archive:
                infos = [i for i in archive.list() if not i.is_directory]
                names = [i.filename for i in infos[:MAX_MEMBERS]]
                total_size = sum(i.uncompressed for i in infos)
        except Exception:
            # py7zr doesn't guarantee a narrow exception type for malformed
            # input the way zipfile.BadZipFile does -- a corrupt/fake 7z can
            # raise anything from its header parser (struct.error,
            # lzma.LZMAError, ...). Same contract as _zip/_tar: anything
            # unparseable just yields no member details, never a crash.
            return {}
        return {"member_count": len(infos), "members": names, "uncompressed_size": total_size}

    def _tar(self, path: Path) -> dict[str, Any]:
        try:
            with tarfile.open(path) as tf:
                members = tf.getmembers()
                names = [m.name for m in members[:MAX_MEMBERS]]
                total_size = sum(m.size for m in members)
        except (tarfile.TarError, OSError):
            return {}
        return {"member_count": len(members), "members": names, "uncompressed_size": total_size}


def console_from_zip_members(path: Path, members: list[str]) -> tuple[str | None, str | None]:
    """If a zip contains a disc image (loose `.iso`/`.img`/`.gcm`, or a raw
    `.bin` dump) identifiable as a single console, return `(console,
    serial)`. Reads each disc-extension member's stream directly (no
    extraction to disk); a zip with no disc-extension members, or one that
    isn't a real zip at all (`.tar.gz`, say), is a cheap no-op. Members
    from more than one console are treated as ambiguous, same as
    `single_console_from_members` above -- `(None, None)` either way.

    `serial` (PS1/PS2 only) comes from whichever candidate member actually
    has the ISO9660 filesystem with `SYSTEM.CNF` on it -- a multi-track
    dump of one disc (several `.bin` tracks + the data track) naturally
    has only one such member, so this never has to choose between
    conflicting serials for a genuine single-disc set.
    """
    candidates = [
        name
        for name in members
        if not name.endswith("/") and Path(name).suffix.lower() in DISC_EXTENSIONS_IN_ARCHIVE
    ]
    if not candidates:
        return None, None

    consoles: set[str] = set()
    serial: str | None = None
    try:
        with zipfile.ZipFile(path) as zf:
            for name in candidates:
                try:
                    with zf.open(name) as member_f:
                        result = console_from_disc_stream(member_f)
                except (zipfile.BadZipFile, KeyError, OSError):
                    result = None
                if result:
                    console, member_serial = result
                    consoles.add(console)
                    serial = member_serial or serial
    except (zipfile.BadZipFile, OSError):
        return None, None

    if len(consoles) == 1:
        return consoles.pop(), serial
    return None, None
