"""Filenames from a per-category template. See PLAN.md section 4.8, ADR 0010.

The default template is `{title}`: a human-readable name (DAT title, PE
ProductName, LLM-proposed name, or the original filename -- whatever
`name_hint` carries), sanitized for Windows but not lowercased or
hyphenated. A date-prefixed slug (`{date}`/`{slug}`, still available for
anyone who wants them in a custom template) actively hurt the one case
that matters most here: a DAT-matched ROM title like ".Hack - Infection
(USA)" is already the exact name EmuDeck/RetroArch/scrapers expect, and
slugifying it into "2026-10-08_hack-infection-usa" destroys that for a
date nobody asked to see. Full metadata-field extraction into arbitrary
template fields beyond these three remains open (PLAN.md section 11).
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from .config import Config
from .identify.types import Evidence
from .route import RouteVerdict

_SLUG_COLLAPSE_RE = re.compile(r"[^a-z0-9]+")
# Windows-reserved characters, plus control characters -- everything else
# (parens, hyphens, periods, non-ASCII) is left alone so a real title stays
# readable. A trailing space or dot is also invalid on Windows, so that's
# stripped after the character substitution, not just leading/trailing
# whitespace.
_WINDOWS_ILLEGAL_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class NamingError(Exception):
    """A template needs a field nothing could fill."""


def slugify(text: str) -> str:
    slug = _SLUG_COLLAPSE_RE.sub("-", text.lower()).strip("-")
    return slug or "untitled"


def sanitize_filename(text: str) -> str:
    """`text`, safe as a Windows filename, with its own casing/spacing/
    punctuation otherwise untouched -- the human-readable counterpart to
    `slugify`.
    """
    cleaned = _WINDOWS_ILLEGAL_RE.sub("", text).strip().rstrip(". ")
    return cleaned or "untitled"


def build_name(
    evidence: Evidence,
    verdict: RouteVerdict,
    category: str,
    config: Config,
    *,
    today: date | None = None,
) -> str:
    source = verdict.name_hint or Path(evidence.original_name).stem
    fields = {
        "date": (today or date.today()).isoformat(),
        "slug": slugify(source),
        "title": sanitize_filename(source),
    }
    template = config.naming.template_for(category)
    try:
        return template.format(**fields)
    except KeyError as e:
        raise NamingError(f"naming template for {category!r} needs field {e}") from e
