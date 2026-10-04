"""Filenames from a per-category template. See PLAN.md section 4.8.

Only the default `{date}_{slug}` template is exercised here: the actual
per-category conventions are still an open decision (PLAN.md section 11),
and full metadata-field extraction into arbitrary template fields is M8
scope. This gives `plan`/`apply` a working, deterministic name now without
pretending the naming system is finished.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from .config import Config
from .identify.types import Evidence
from .route import RouteVerdict

_SLUG_COLLAPSE_RE = re.compile(r"[^a-z0-9]+")


class NamingError(Exception):
    """A template needs a field nothing could fill."""


def slugify(text: str) -> str:
    slug = _SLUG_COLLAPSE_RE.sub("-", text.lower()).strip("-")
    return slug or "untitled"


def build_name(
    evidence: Evidence,
    verdict: RouteVerdict,
    category: str,
    config: Config,
    *,
    today: date | None = None,
) -> str:
    source = verdict.name_hint or Path(evidence.original_name).stem
    fields = {"date": (today or date.today()).isoformat(), "slug": slugify(source)}
    template = config.naming.template_for(category)
    try:
        return template.format(**fields)
    except KeyError as e:
        raise NamingError(f"naming template for {category!r} needs field {e}") from e
