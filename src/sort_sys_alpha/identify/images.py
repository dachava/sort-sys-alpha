"""Image dimensions, EXIF, and a screenshot/photo/wallpaper heuristic.
See PLAN.md section 4.3.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import ExifTags, Image, UnidentifiedImageError

from .base import Extractor
from .types import Evidence

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic", ".tiff"}

EXIF_FIELDS = {"Make", "Model", "DateTimeOriginal", "DateTime", "Software"}

# Common full-screen / monitor resolutions: a strong screenshot signal when
# there's no camera EXIF to say otherwise.
SCREEN_RESOLUTIONS = {
    (1280, 720), (1366, 768), (1920, 1080), (2560, 1440), (3840, 2160),
    (2560, 1600), (3440, 1440),
}


class ImageExtractor(Extractor):
    name = "image"
    priority = 40

    def can_handle(self, evidence: Evidence) -> bool:
        return evidence.extension in IMAGE_EXTENSIONS

    def extract(self, path: Path, evidence: Evidence) -> dict[str, Any]:
        try:
            with Image.open(path) as img:
                width, height = img.size
                exif = self._read_exif(img)
        except (UnidentifiedImageError, OSError):
            return {}

        result: dict[str, Any] = {"width": width, "height": height, "exif": exif}
        result["looks_like_screenshot"] = self._looks_like_screenshot(
            evidence.original_name, width, height, exif
        )
        return result

    def _read_exif(self, img: Image.Image) -> dict[str, str]:
        raw = img.getexif()
        result: dict[str, str] = {}
        for tag_id, value in raw.items():
            name = ExifTags.TAGS.get(tag_id)
            if name in EXIF_FIELDS and isinstance(value, (str, bytes)):
                result[name] = value.decode(errors="replace") if isinstance(value, bytes) else value
        return result

    def _looks_like_screenshot(
        self, name: str, width: int, height: int, exif: dict[str, str]
    ) -> bool:
        if "screenshot" in name.lower() or "screen shot" in name.lower():
            return True
        has_camera_exif = "Make" in exif or "Model" in exif
        return not has_camera_exif and (width, height) in SCREEN_RESOLUTIONS
