"""The extractor plugin contract. See PLAN.md section 4.3."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .types import Evidence


class Extractor(ABC):
    name: str
    priority: int = 100  # lower runs first; the first match wins

    @abstractmethod
    def can_handle(self, evidence: Evidence) -> bool: ...

    @abstractmethod
    def extract(self, path: Path, evidence: Evidence) -> dict[str, Any]: ...
