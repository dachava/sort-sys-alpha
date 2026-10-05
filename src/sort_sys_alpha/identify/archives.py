"""Archive member listing, via stdlib `zipfile`/`tarfile`. Never extracts.
See PLAN.md section 4.3.

`.7z` isn't in scope yet (no stdlib support, and py7zr is an extra
dependency this milestone doesn't need) — it falls through to the
true_type/extension-only evidence from the unknown-type extractor instead of
getting a member listing. `.rar` is the same story for *listing* members,
but it's still routed deterministically (PLAN.md rule 1: rules before the
model) since classifying "this is an archive" by extension needs no library
at all — `extract()` just returns no member details for it.
"""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path
from typing import Any

from .base import Extractor
from .types import Evidence

MAX_MEMBERS = 20

ZIP_EXTENSIONS = {".zip"}
TAR_EXTENSIONS = {".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz"}
RAR_EXTENSIONS = {".rar"}


class ArchiveExtractor(Extractor):
    name = "archive"
    priority = 45

    def can_handle(self, evidence: Evidence) -> bool:
        return (
            evidence.extension in ZIP_EXTENSIONS
            or evidence.extension in RAR_EXTENSIONS
            or any(evidence.original_name.lower().endswith(suffix) for suffix in TAR_EXTENSIONS)
        )

    def extract(self, path: Path, evidence: Evidence) -> dict[str, Any]:
        if evidence.extension in ZIP_EXTENSIONS:
            return self._zip(path)
        if evidence.extension in RAR_EXTENSIONS:
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

    def _tar(self, path: Path) -> dict[str, Any]:
        try:
            with tarfile.open(path) as tf:
                members = tf.getmembers()
                names = [m.name for m in members[:MAX_MEMBERS]]
                total_size = sum(m.size for m in members)
        except (tarfile.TarError, OSError):
            return {}
        return {"member_count": len(members), "members": names, "uncompressed_size": total_size}
