"""Fallback for anything no other extractor claimed: a raw byte preview,
so the model has *something* to go on. See PLAN.md section 4.3.
"""

from __future__ import annotations

import string
from pathlib import Path
from typing import Any

from .base import Extractor
from .types import Evidence

PREVIEW_BYTES = 512
PRINTABLE = set(string.printable.encode())


def _printable_preview(raw: bytes) -> str:
    return "".join(chr(b) if b in PRINTABLE else "." for b in raw)


class UnknownExtractor(Extractor):
    name = "unknown"
    priority = 1000  # always matches; runs only if nothing else did

    def can_handle(self, evidence: Evidence) -> bool:
        return True

    def extract(self, path: Path, evidence: Evidence) -> dict[str, Any]:
        try:
            with path.open("rb") as f:
                raw = f.read(PREVIEW_BYTES)
        except OSError:
            return {}
        return {"hex_preview": raw.hex(), "printable_preview": _printable_preview(raw)}
