"""`.safetensors` ML model weight files. See PLAN.md section 4.3.

No fixed magic bytes, but the format's own structure is cheap to check: an
8-byte little-endian length prefix followed by that many bytes of JSON
header metadata, so byte 8 is always the JSON object's opening `{`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Extractor
from .types import Evidence


def _read_at(path: Path, offset: int, length: int) -> bytes:
    try:
        with path.open("rb") as f:
            f.seek(offset)
            return f.read(length)
    except OSError:
        return b""


def _looks_like_safetensors(path: Path, file_size: int) -> bool:
    header = _read_at(path, 0, 9)
    if len(header) < 9:
        return False
    header_len = int.from_bytes(header[:8], "little")
    return header[8:9] == b"{" and 0 < header_len <= file_size


class MlWeightsExtractor(Extractor):
    name = "ml_weights"
    priority = 44

    def can_handle(self, evidence: Evidence) -> bool:
        return evidence.extension == ".safetensors" and _looks_like_safetensors(
            evidence.path, evidence.size
        )

    def extract(self, path: Path, evidence: Evidence) -> dict[str, Any]:
        return {"format": "safetensors"}
