"""The evidence bundle every scanned item gets before any model is involved.

See PLAN.md section 4.3 for the signal table this type is built from.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Evidence(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: Path
    original_name: str
    extension: str
    size: int
    created: datetime
    modified: datetime
    true_type: str | None = None
    source_host: str | None = None
    referrer_host: str | None = None
    kind: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
