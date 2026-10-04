"""Download provenance from the Zone.Identifier alternate data stream.

Windows writes this NTFS ADS next to every file downloaded from the web, as
`<path>:Zone.Identifier`, holding an INI-style `[ZoneTransfer]` section with
`HostUrl` and `ReferrerUrl`. `open()` can read it directly on Windows with no
extra library (PLAN.md section 3); on any other OS the stream doesn't exist,
so this is naturally a no-op there.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse


def _hostname(url: str | None) -> str | None:
    if not url:
        return None
    return urlparse(url).hostname


def parse_zone_identifier_text(text: str) -> dict[str, str | None]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            values[key.strip().lower()] = value.strip()
    return {
        "source_host": _hostname(values.get("hosturl")),
        "referrer_host": _hostname(values.get("referrerurl")),
    }


def read_zone_identifier(path: Path) -> dict[str, str | None]:
    """Return {"source_host", "referrer_host"}, both None if there's no ADS."""
    stream_path = Path(f"{path}:Zone.Identifier")
    try:
        text = stream_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"source_host": None, "referrer_host": None}
    return parse_zone_identifier_text(text)
