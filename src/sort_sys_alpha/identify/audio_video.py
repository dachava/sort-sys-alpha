"""Audio tags/duration via `mutagen`; video duration via `ffprobe` if present.
See PLAN.md section 4.3.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import mutagen

from .base import Extractor
from .types import Evidence

AUDIO_EXTENSIONS = {".mp3", ".flac", ".ogg", ".wav", ".m4a", ".aac", ".wma"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm"}

TAG_FIELDS = {"title": "title", "artist": "artist", "album": "album", "date": "date"}


class AudioVideoExtractor(Extractor):
    name = "audio_video"
    priority = 42

    def can_handle(self, evidence: Evidence) -> bool:
        return evidence.extension in AUDIO_EXTENSIONS or evidence.extension in VIDEO_EXTENSIONS

    def extract(self, path: Path, evidence: Evidence) -> dict[str, Any]:
        if evidence.extension in AUDIO_EXTENSIONS:
            return self._audio(path)
        return self._video(path)

    def _audio(self, path: Path) -> dict[str, Any]:
        try:
            audio = mutagen.File(path, easy=True)
        except mutagen.MutagenError:
            return {}
        if audio is None:
            return {}

        result: dict[str, Any] = {}
        if audio.info is not None and getattr(audio.info, "length", None):
            result["duration_s"] = round(audio.info.length, 1)
        for field, tag_key in TAG_FIELDS.items():
            values = audio.get(tag_key)
            if values:
                result[field] = values[0]
        return result

    def _video(self, path: Path) -> dict[str, Any]:
        ffprobe = shutil.which("ffprobe")
        if ffprobe is None:
            return {}
        try:
            output = subprocess.run(
                [ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
            data = json.loads(output.stdout)
        except (subprocess.SubprocessError, OSError, json.JSONDecodeError):
            return {}

        duration = data.get("format", {}).get("duration")
        return {"duration_s": round(float(duration), 1)} if duration else {}
