"""Windows PE version info. See PLAN.md section 4.3.

MSI property extraction is deferred: Python's `msilib` was removed in 3.13,
and MSI files are OLE compound documents, so reading their properties needs
an `olefile`-based reader this milestone doesn't add. An `.msi` still gets
routed correctly by extension/true_type in the rules tier; it just won't
have ProductName/Version evidence yet.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pefile

from .base import Extractor
from .types import Evidence

PE_EXTENSIONS = {".exe", ".dll", ".sys"}

VERSION_FIELDS = ("ProductName", "CompanyName", "FileVersion", "ProductVersion", "FileDescription")


class ExecutableExtractor(Extractor):
    name = "executable"
    priority = 20

    def can_handle(self, evidence: Evidence) -> bool:
        return evidence.extension in PE_EXTENSIONS

    def extract(self, path: Path, evidence: Evidence) -> dict[str, Any]:
        try:
            pe = pefile.PE(str(path), fast_load=True)
            pe.parse_data_directories(
                directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]]
            )
        except pefile.PEFormatError:
            return {"is_pe": False}

        try:
            info = self._version_info(pe)
        finally:
            pe.close()
        return {"is_pe": True, **info}

    def _version_info(self, pe: pefile.PE) -> dict[str, str]:
        result: dict[str, str] = {}
        for file_info in getattr(pe, "FileInfo", []):
            for entry in file_info:
                if entry.Key != b"StringFileInfo":
                    continue
                for table in entry.StringTable:
                    for key, value in table.entries.items():
                        key_str = key.decode() if isinstance(key, bytes) else key
                        if key_str in VERSION_FIELDS:
                            result[key_str] = value.decode() if isinstance(value, bytes) else value
        return result
