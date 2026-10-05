"""PDF metadata, page count, and a text preview. See PLAN.md section 4.3.

Rendering page 1 for scanned PDFs (vision input) is M6 scope, not needed
until there's an LLM call to hand it to.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .base import Extractor
from .types import Evidence

PREVIEW_LINES = 40

# pypdf logs xref-table repairs (e.g. "Ignoring wrong pointing object N 0
# (offset 0)") as WARNING through the standard `logging` module, which
# Python prints straight to stderr by default. These are routine on
# real-world PDFs -- pypdf still parses them fine -- and would otherwise
# spam every scan/plan/run; ERROR+ still surfaces anything that actually
# stops extraction from working.
logging.getLogger("pypdf").setLevel(logging.ERROR)


class PdfExtractor(Extractor):
    name = "pdf"
    priority = 35

    def can_handle(self, evidence: Evidence) -> bool:
        return evidence.extension == ".pdf" or evidence.true_type == "application/pdf"

    def extract(self, path: Path, evidence: Evidence) -> dict[str, Any]:
        try:
            reader = PdfReader(str(path))
        except (PdfReadError, OSError):
            return {}

        result: dict[str, Any] = {"page_count": len(reader.pages)}
        meta = reader.metadata
        if meta:
            if meta.title:
                result["title"] = meta.title
            if meta.author:
                result["author"] = meta.author

        if reader.pages:
            try:
                text = reader.pages[0].extract_text() or ""
            except Exception:  # pypdf can raise various parser-specific errors
                text = ""
            lines = text.splitlines()[:PREVIEW_LINES]
            result["text_preview"] = "\n".join(lines)
            result["is_scanned"] = len(text.strip()) == 0

        return result
