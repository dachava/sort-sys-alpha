"""Log detection: `.log` files, and `.txt` files that are really logs.
See PLAN.md section 4.3.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .base import Extractor
from .types import Evidence

PEEK_BYTES = 4096
PREVIEW_LINES = 40

TIMESTAMP_RE = re.compile(
    r"^\[?\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}"  # 2024-01-01 12:00:00 / ISO8601
    r"|^\[?\d{2}/\d{2}/\d{4}[ T]\d{2}:\d{2}:\d{2}"  # 01/01/2024 12:00:00
)
LOG_LEVEL_RE = re.compile(r"\b(TRACE|DEBUG|INFO|WARN(?:ING)?|ERROR|FATAL|CRITICAL)\b")


def _read_lines(path: Path) -> list[str]:
    try:
        with path.open("rb") as f:
            raw = f.read(PEEK_BYTES)
    except OSError:
        return []
    text = raw.decode("utf-8", errors="replace")
    return [line for line in text.splitlines() if line.strip()]


def looks_like_log(lines: list[str]) -> bool:
    sample = lines[:20]
    if not sample:
        return False
    matches = sum(1 for line in sample if TIMESTAMP_RE.search(line) or LOG_LEVEL_RE.search(line))
    return matches / len(sample) >= 0.5


class LogExtractor(Extractor):
    name = "log"
    priority = 32

    def can_handle(self, evidence: Evidence) -> bool:
        if evidence.extension == ".log":
            return True
        if evidence.extension == ".txt":
            return looks_like_log(_read_lines(evidence.path))
        return False

    def extract(self, path: Path, evidence: Evidence) -> dict[str, Any]:
        lines = _read_lines(path)
        return {"line_preview": "\n".join(lines[:PREVIEW_LINES])}
