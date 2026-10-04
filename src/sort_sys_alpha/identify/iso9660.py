"""Minimal ISO9660 (ECMA-119) reader: just enough to get the volume label and
the root directory's entry names, which is all PLAN.md section 4.9 needs to
tell a PS1/PS2/PSP disc from a generic ISO. No dependency on `pycdlib`.

Only handles plain 2048-byte-sector images (CD-ROM mode 1 / DVD). Raw
CD sector formats (.bin/.cue tracks, .gdi, .ccd) are out of scope here —
see identify/discs.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SECTOR_SIZE = 2048
PVD_SECTOR = 16


@dataclass
class PrimaryVolumeDescriptor:
    volume_id: str
    root_extent_lba: int
    root_data_length: int


def read_pvd(path: Path) -> PrimaryVolumeDescriptor | None:
    try:
        with path.open("rb") as f:
            f.seek(PVD_SECTOR * SECTOR_SIZE)
            sector = f.read(SECTOR_SIZE)
    except OSError:
        return None

    if len(sector) < 190 or sector[0] != 1 or sector[1:6] != b"CD001":
        return None

    volume_id = sector[40:72].decode("ascii", errors="replace").strip()
    root_record = sector[156:190]
    root_extent_lba = int.from_bytes(root_record[2:6], "little")
    root_data_length = int.from_bytes(root_record[10:14], "little")
    return PrimaryVolumeDescriptor(volume_id, root_extent_lba, root_data_length)


@dataclass
class DirectoryRecord:
    name: str
    extent_lba: int
    data_length: int


def _iter_root_records(path: Path, pvd: PrimaryVolumeDescriptor) -> list[DirectoryRecord]:
    try:
        with path.open("rb") as f:
            f.seek(pvd.root_extent_lba * SECTOR_SIZE)
            data = f.read(pvd.root_data_length)
    except OSError:
        return []

    records: list[DirectoryRecord] = []
    offset = 0
    while offset < len(data):
        record_len = data[offset]
        if record_len == 0:
            # Records never cross a sector boundary; skip to the next one.
            offset = (offset // SECTOR_SIZE + 1) * SECTOR_SIZE
            continue
        file_id_len = data[offset + 32]
        raw_name = data[offset + 33 : offset + 33 + file_id_len]
        if raw_name not in (b"\x00", b"\x01"):  # "." and ".."
            name = raw_name.decode("ascii", errors="replace").split(";")[0].upper()
            extent = int.from_bytes(data[offset + 2 : offset + 6], "little")
            length = int.from_bytes(data[offset + 10 : offset + 14], "little")
            records.append(DirectoryRecord(name, extent, length))
        offset += record_len
    return records


def list_root_entries(path: Path, pvd: PrimaryVolumeDescriptor) -> set[str]:
    """Names in the root directory, uppercased, with any ";N" version suffix stripped."""
    return {record.name for record in _iter_root_records(path, pvd)}


def read_root_file(path: Path, pvd: PrimaryVolumeDescriptor, name: str) -> bytes | None:
    """Read a root-level file's contents by name (case-insensitive, no ";N" needed)."""
    for record in _iter_root_records(path, pvd):
        if record.name == name.upper():
            return _read_extent(path, record.extent_lba, record.data_length)
    return None


def _read_extent(path: Path, extent_lba: int, length: int) -> bytes | None:
    try:
        with path.open("rb") as f:
            f.seek(extent_lba * SECTOR_SIZE)
            return f.read(length)
    except OSError:
        return None
