"""Torrent name, via a minimal bencode decoder (no extra dependency).
See PLAN.md section 4.3.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Extractor
from .types import Evidence


class BencodeError(Exception):
    pass


def _decode(data: bytes, pos: int) -> tuple[Any, int]:
    marker = data[pos : pos + 1]
    if marker == b"i":
        end = data.index(b"e", pos)
        return int(data[pos + 1 : end]), end + 1
    if marker == b"l":
        items = []
        pos += 1
        while data[pos : pos + 1] != b"e":
            item, pos = _decode(data, pos)
            items.append(item)
        return items, pos + 1
    if marker == b"d":
        result: dict[bytes, Any] = {}
        pos += 1
        while data[pos : pos + 1] != b"e":
            key, pos = _decode(data, pos)
            value, pos = _decode(data, pos)
            result[key] = value
        return result, pos + 1
    if marker.isdigit():
        colon = data.index(b":", pos)
        length = int(data[pos:colon])
        start = colon + 1
        return data[start : start + length], start + length
    raise BencodeError(f"unexpected byte {marker!r} at offset {pos}")


def decode_torrent(data: bytes) -> dict[bytes, Any]:
    value, _ = _decode(data, 0)
    if not isinstance(value, dict):
        raise BencodeError("top-level bencode value is not a dict")
    return value


class TorrentExtractor(Extractor):
    name = "torrent"
    priority = 25

    def can_handle(self, evidence: Evidence) -> bool:
        return evidence.extension == ".torrent"

    def extract(self, path: Path, evidence: Evidence) -> dict[str, Any]:
        try:
            data = path.read_bytes()
            torrent = decode_torrent(data)
        except (OSError, BencodeError, IndexError, ValueError):
            return {}

        info = torrent.get(b"info", {})
        name = info.get(b"name")
        files = info.get(b"files")
        result: dict[str, Any] = {}
        if name is not None:
            result["name"] = name.decode("utf-8", errors="replace")
        if isinstance(files, list):
            result["file_count"] = len(files)
        return result
