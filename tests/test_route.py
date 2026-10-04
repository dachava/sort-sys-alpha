from pathlib import Path

from sort_sys_alpha.config import Config
from sort_sys_alpha.identify import build_evidence
from sort_sys_alpha.route import route


def test_user_rule_takes_precedence_over_builtin(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("hello")
    config = Config.model_validate(
        {"rules": [{"match": {"ext": [".txt"]}, "folder": "Other"}]}
    )

    verdict = route(build_evidence(path), config)
    assert verdict.category == "Other"
    assert "config rule" in verdict.reason


def test_builtin_image_routing(tmp_path: Path) -> None:
    from fixtures.make import make_png

    path = tmp_path / "photo.png"
    make_png(path)
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "Images"
    assert verdict.confidence == 1.0


def test_builtin_note_vs_code_file(tmp_path: Path) -> None:
    note = tmp_path / "todo.txt"
    note.write_text("buy milk")
    code = tmp_path / "script.py"
    code.write_text("print('hi')")

    assert route(build_evidence(note), Config()).category == "Documents/Notes"
    assert route(build_evidence(code), Config()) is None  # no category for code files yet


def test_builtin_installer_extension(tmp_path: Path) -> None:
    path = tmp_path / "setup.exe"
    path.write_bytes(b"\x00" * 20)
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "Installers"


def test_rom_header_verified_routes_to_console_folder(tmp_path: Path) -> None:
    path = tmp_path / "game.nes"
    path.write_bytes(b"NES\x1a" + b"\x00" * 50)
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "ROMs/nes"


def test_rom_failed_verification_is_not_routed(tmp_path: Path) -> None:
    path = tmp_path / "fake.nes"
    path.write_bytes(b"\x00" * 50)
    assert route(build_evidence(path), Config()) is None


def test_extension_only_console_still_routes(tmp_path: Path) -> None:
    path = tmp_path / "game.sfc"
    path.write_bytes(b"\x00" * 50)
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "ROMs/snes"


def test_generic_iso_routes_to_isos(tmp_path: Path) -> None:
    from fixtures.make import make_iso9660

    path = tmp_path / "linux.iso"
    make_iso9660(path, volume_id="LINUX")
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "ISOs"


def test_console_disc_routes_to_roms(tmp_path: Path) -> None:
    from fixtures.make import make_iso9660

    path = tmp_path / "game.iso"
    make_iso9660(path, volume_id="GAME", root_files={"SYSTEM.CNF": b"BOOT2 = x;1\r\n"})
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "ROMs/ps2"


def test_archive_routes_to_archives(tmp_path: Path) -> None:
    from fixtures.make import make_zip

    path = tmp_path / "stuff.zip"
    make_zip(path, {"a.txt": b"hi"})
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "Archives"


def test_unclaimed_kind_is_unrouted(tmp_path: Path) -> None:
    path = tmp_path / "mystery.xyz123"
    path.write_bytes(b"\x01\x02\x03")
    assert route(build_evidence(path), Config()) is None
