"""Basic filesystem stats, always collected. See PLAN.md section 4.3."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def get_stats(path: Path) -> dict[str, Any]:
    st = path.stat()
    return {
        "original_name": path.name,
        "extension": path.suffix.lower(),
        "size": st.st_size,
        "created": datetime.fromtimestamp(st.st_ctime, tz=UTC),
        "modified": datetime.fromtimestamp(st.st_mtime, tz=UTC),
    }
