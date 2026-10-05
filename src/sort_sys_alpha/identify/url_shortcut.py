"""Windows Internet Shortcut (.url) files. See PLAN.md section 4.3.

Plain-text INI-style files Windows creates for a saved link: a
`[InternetShortcut]` section with a `URL=` line. Identified by content, not
just the extension, the same way `logs.py` disambiguates a log-shaped
".txt" from a plain note.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Extractor
from .types import Evidence

PEEK_BYTES = 512
_MARKER = "[internetshortcut]"


def _peek(path: Path) -> str:
    try:
        with path.open("rb") as f:
            raw = f.read(PEEK_BYTES)
    except OSError:
        return ""
    return raw.decode("utf-8", errors="replace")


class UrlShortcutExtractor(Extractor):
    name = "url_shortcut"
    priority = 44

    def can_handle(self, evidence: Evidence) -> bool:
        if evidence.extension != ".url":
            return False
        return _peek(evidence.path).lstrip().lower().startswith(_MARKER)

    def extract(self, path: Path, evidence: Evidence) -> dict[str, Any]:
        for line in _peek(path).splitlines():
            if line.strip().lower().startswith("url="):
                return {"target_url": line.split("=", 1)[1].strip()}
        return {}
