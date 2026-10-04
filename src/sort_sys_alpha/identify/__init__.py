"""Evidence extractors: one plugin per file type, each exposing
`can_handle(evidence) -> bool` and `extract(path, evidence) -> dict`
(PLAN.md section 4.3). `build_evidence` runs the universal signals first,
then the first matching type-specific extractor, falling back to
`UnknownExtractor` if nothing else claimed the file.
"""

from __future__ import annotations

from pathlib import Path

from .. import items as _items
from . import download_source, magic, stats
from .archives import ArchiveExtractor
from .audio_video import AudioVideoExtractor
from .base import Extractor
from .disk_images import DiskImageExtractor
from .executables import ExecutableExtractor
from .fonts import FontExtractor
from .images import ImageExtractor
from .logs import LogExtractor
from .office import OfficeExtractor
from .pdf import PdfExtractor
from .roms import RomExtractor
from .text import TextExtractor
from .torrents import TorrentExtractor
from .types import Evidence
from .unknown import UnknownExtractor

EXTRACTORS: list[Extractor] = sorted(
    [
        RomExtractor(),
        DiskImageExtractor(),
        ExecutableExtractor(),
        TorrentExtractor(),
        FontExtractor(),
        LogExtractor(),
        ArchiveExtractor(),
        AudioVideoExtractor(),
        PdfExtractor(),
        OfficeExtractor(),
        ImageExtractor(),
        TextExtractor(),
        UnknownExtractor(),
    ],
    key=lambda e: e.priority,
)


def build_evidence(path: Path) -> Evidence:
    """Run the universal signals, then dispatch to the first matching extractor."""
    base = stats.get_stats(path)
    true_type = magic.get_true_type(path)
    zone = download_source.read_zone_identifier(path)

    evidence = Evidence(path=path, true_type=true_type, **base, **zone)

    for extractor in EXTRACTORS:
        if extractor.can_handle(evidence):
            evidence.kind = extractor.name
            evidence.details = extractor.extract(path, evidence)
            break

    return evidence


def identify_item(item: _items.ScanItem) -> Evidence:
    """Evidence for anything `scan` produced: a lone file, or a file group.

    A group's evidence is built from its primary (defining) file's stats,
    but `kind`/`details` describe the group as a whole rather than
    whatever generic extractor would otherwise claim the sheet file itself
    (e.g. a `.cue` is plain text, but its evidence should say "disc group",
    not "text file").
    """
    if isinstance(item, _items.FileItem):
        return build_evidence(item.path)

    base = stats.get_stats(item.primary)
    evidence = Evidence(path=item.primary, true_type=magic.get_true_type(item.primary), **base)
    evidence.kind = "disc_group"
    evidence.details = {
        "group_kind": item.kind,
        "members": [str(p) for p in item.members],
        "member_count": len(item.members),
        "total_size": sum(p.stat().st_size for p in item.members if p.exists()),
    }
    return evidence
