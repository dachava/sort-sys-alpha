"""Text/code/config preview and language-by-extension. See PLAN.md section 4.3."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Extractor
from .types import Evidence

PREVIEW_LINES = 40

LANGUAGE_BY_EXTENSION = {
    ".py": "python", ".js": "javascript", ".ts": "typescript", ".tsx": "typescript",
    ".jsx": "javascript", ".json": "json", ".yaml": "yaml", ".yml": "yaml",
    ".toml": "toml", ".ini": "ini", ".cfg": "ini", ".tf": "terraform",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".java": "java",
    ".go": "go", ".rs": "rust", ".sh": "shell", ".ps1": "powershell",
    ".sql": "sql", ".rb": "ruby", ".php": "php", ".css": "css",
    ".html": "html", ".xml": "xml", ".md": "markdown", ".csv": "csv",
    ".txt": None,
}

TEXT_EXTENSIONS = set(LANGUAGE_BY_EXTENSION)


class TextExtractor(Extractor):
    name = "text"
    priority = 50

    def can_handle(self, evidence: Evidence) -> bool:
        return evidence.extension in TEXT_EXTENSIONS

    def extract(self, path: Path, evidence: Evidence) -> dict[str, Any]:
        try:
            with path.open("rb") as f:
                raw = f.read(8192)
        except OSError:
            return {}

        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()[:PREVIEW_LINES]
        return {
            "language": LANGUAGE_BY_EXTENSION.get(evidence.extension),
            "text_preview": "\n".join(lines),
        }
