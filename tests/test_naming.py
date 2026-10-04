from datetime import date
from pathlib import Path

import pytest

from sort_sys_alpha.config import Config
from sort_sys_alpha.identify import build_evidence
from sort_sys_alpha.naming import NamingError, build_name, slugify
from sort_sys_alpha.route import RouteVerdict


def test_slugify_basic() -> None:
    assert slugify("Hello, World!") == "hello-world"
    assert slugify("  multiple   spaces  ") == "multiple-spaces"
    assert slugify("") == "untitled"
    assert slugify("###") == "untitled"


def test_default_template_uses_original_name_when_no_hint(tmp_path: Path) -> None:
    path = tmp_path / "My Cool Photo.jpg"
    path.write_bytes(b"\x00")
    evidence = build_evidence(path)
    verdict = RouteVerdict("Images", 1.0, "image file")

    name = build_name(evidence, verdict, "Images", Config(), today=date(2026, 1, 2))
    assert name == "2026-01-02_my-cool-photo"


def test_name_hint_takes_precedence(tmp_path: Path) -> None:
    path = tmp_path / "IMG_4031.pdf"
    path.write_bytes(b"\x00")
    evidence = build_evidence(path)
    verdict = RouteVerdict("Documents", 1.0, "pdf", name_hint="Chase Statement Aug 2026")

    name = build_name(evidence, verdict, "Documents", Config(), today=date(2026, 1, 2))
    assert name == "2026-01-02_chase-statement-aug-2026"


def test_missing_template_field_raises_naming_error(tmp_path: Path) -> None:
    path = tmp_path / "game.nes"
    path.write_bytes(b"\x00")
    evidence = build_evidence(path)
    verdict = RouteVerdict("ROMs/nes", 1.0, "rom")
    config = Config.model_validate({"naming": {"ROMs/nes": "{title} ({region})"}})

    with pytest.raises(NamingError):
        build_name(evidence, verdict, "ROMs/nes", config)
