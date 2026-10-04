"""Font family/style, via the `name` table. See PLAN.md section 4.3."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fontTools.ttLib import TTFont, TTLibError

from .base import Extractor
from .types import Evidence

FONT_EXTENSIONS = {".ttf", ".otf", ".ttc", ".woff", ".woff2"}

# Common name-table ID -> field we care about.
NAME_IDS = {1: "family", 2: "style", 4: "full_name", 16: "typographic_family"}


class FontExtractor(Extractor):
    name = "font"
    priority = 30

    def can_handle(self, evidence: Evidence) -> bool:
        return evidence.extension in FONT_EXTENSIONS

    def extract(self, path: Path, evidence: Evidence) -> dict[str, Any]:
        try:
            font = TTFont(str(path), lazy=True, fontNumber=0)
        except (TTLibError, OSError):
            return {}

        result: dict[str, Any] = {}
        try:
            name_table = font.get("name")
            if name_table is not None:
                for record in name_table.names:
                    field = NAME_IDS.get(record.nameID)
                    if field and field not in result:
                        try:
                            result[field] = record.toUnicode()
                        except UnicodeDecodeError:
                            continue
        finally:
            font.close()
        return result
