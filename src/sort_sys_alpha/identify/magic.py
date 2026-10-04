"""True file type via magic bytes, independent of extension. See PLAN.md section 4.3."""

from __future__ import annotations

from pathlib import Path

import puremagic


def get_true_type(path: Path) -> str | None:
    try:
        matches = puremagic.magic_file(str(path))
    except (puremagic.PureError, ValueError, OSError):
        return None
    if not matches:
        return None
    return matches[0].mime_type or None
