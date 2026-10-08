from datetime import date
from pathlib import Path

import pytest

from sort_sys_alpha.config import Config
from sort_sys_alpha.identify import build_evidence
from sort_sys_alpha.naming import NamingError, build_name, sanitize_filename, slugify
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
    assert name == "My Cool Photo"


def test_name_hint_takes_precedence(tmp_path: Path) -> None:
    path = tmp_path / "IMG_4031.pdf"
    path.write_bytes(b"\x00")
    evidence = build_evidence(path)
    verdict = RouteVerdict("Documents", 1.0, "pdf", name_hint="Chase Statement Aug 2026")

    name = build_name(evidence, verdict, "Documents", Config(), today=date(2026, 1, 2))
    assert name == "Chase Statement Aug 2026"


def test_sanitize_filename_strips_windows_illegal_characters() -> None:
    assert sanitize_filename('Report: "Q1" <final>?') == "Report Q1 final"


def test_sanitize_filename_keeps_casing_and_punctuation() -> None:
    assert sanitize_filename(".Hack - Infection (USA)") == ".Hack - Infection (USA)"


def test_sanitize_filename_strips_trailing_dot_and_space() -> None:
    assert sanitize_filename("report. ") == "report"


def test_sanitize_filename_empty_after_cleaning_is_untitled() -> None:
    assert sanitize_filename('???') == "untitled"


def test_rom_dat_title_is_used_verbatim_not_slugified(tmp_path: Path) -> None:
    path = tmp_path / "game.iso"
    path.write_bytes(b"\x00")
    evidence = build_evidence(path)
    verdict = RouteVerdict("ROMs/ps2", 1.0, "disc", name_hint=".Hack - Infection (USA)")

    name = build_name(evidence, verdict, "ROMs/ps2", Config(), today=date(2026, 1, 2))
    assert name == ".Hack - Infection (USA)"


def test_per_category_override_falls_back_to_slug(tmp_path: Path) -> None:
    path = tmp_path / "setup.exe"
    path.write_bytes(b"\x00")
    evidence = build_evidence(path)
    verdict = RouteVerdict("Installers", 1.0, "installer", name_hint="7-Zip 24.08 x64")
    config = Config.model_validate({"naming": {"Installers": "{slug}"}})

    name = build_name(evidence, verdict, "Installers", config, today=date(2026, 1, 2))
    assert name == "7-zip-24-08-x64"


def test_missing_template_field_raises_naming_error(tmp_path: Path) -> None:
    path = tmp_path / "game.nes"
    path.write_bytes(b"\x00")
    evidence = build_evidence(path)
    verdict = RouteVerdict("ROMs/nes", 1.0, "rom")
    config = Config.model_validate({"naming": {"ROMs/nes": "{title} ({region})"}})

    with pytest.raises(NamingError):
        build_name(evidence, verdict, "ROMs/nes", config)
