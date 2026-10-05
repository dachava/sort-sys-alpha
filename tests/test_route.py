import json
from pathlib import Path

from sort_sys_alpha.config import Config
from sort_sys_alpha.identify import build_evidence
from sort_sys_alpha.items import FileGroup, FileItem, FolderUnit
from sort_sys_alpha.route import resolve, route


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
    assert verdict.source == "rule"


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


def test_rar_routes_to_archives(tmp_path: Path) -> None:
    path = tmp_path / "stuff.rar"
    path.write_bytes(b"Rar!\x1a\x07\x01\x00" + b"\x00" * 20)
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "Archives"


def test_7z_routes_to_archives(tmp_path: Path) -> None:
    path = tmp_path / "stuff.7z"
    path.write_bytes(b"7z\xbc\xaf\x27\x1c" + b"\x00" * 20)
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "Archives"


def test_wii_wad_routes_to_roms_wii(tmp_path: Path) -> None:
    path = tmp_path / "channel.wad"
    path.write_bytes(bytes.fromhex("00000020") + b"Is" + b"\x00" * 24)
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "ROMs/wii"


def test_wbfs_routes_to_roms_wii(tmp_path: Path) -> None:
    from fixtures.make import make_disc_magic

    path = tmp_path / "game.wbfs"
    make_disc_magic(path, offset=0x0, magic=b"WBFS")
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "ROMs/wii"


def test_mame_romdef_routes_to_other_with_suggest_delete(tmp_path: Path) -> None:
    path = tmp_path / "ctomaday.rc"
    path.write_text(
        '#mame set of  ctomaday\n'
        'game  ctomaday  MVS "Captain Tomaday"\n'
        'CPU 0x200000\n'
        '249-p1.bin 0x100000 0x100000 NORM\n'
        'END\n'
    )
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "Other"
    assert verdict.suggest_delete is True
    assert verdict.name_hint == "Captain Tomaday"


def test_unclaimed_kind_is_unrouted(tmp_path: Path) -> None:
    path = tmp_path / "mystery.xyz123"
    path.write_bytes(b"\x01\x02\x03")
    assert route(build_evidence(path), Config()) is None


def _llm_config(base_url: str) -> Config:
    return Config.model_validate({"model": {"backend": "ollama", "ollama": {"base_url": base_url}}})


def test_resolve_folder_unit_never_calls_the_model(tmp_path: Path) -> None:
    root = tmp_path / "MyApp"
    root.mkdir()
    (root / "setup.exe").write_bytes(b"\x00")
    unit = FolderUnit(root, "Installers", "extracted app markers", (root / "setup.exe",))

    # A loopback address nothing listens on -- resolve() must not reach it.
    config = _llm_config("http://127.0.0.1:1")
    verdict, reason = resolve(unit, build_evidence(root), config)
    assert verdict.category == "Installers"
    assert reason is None


def test_resolve_file_group_skips_the_llm_tier(tmp_path: Path) -> None:
    cue = tmp_path / "game.cue"
    cue.write_text('FILE "game.bin" BINARY\n')
    group = FileGroup("cue_bin", cue, (cue, tmp_path / "game.bin"))

    config = _llm_config("http://127.0.0.1:1")  # must not be contacted
    verdict, reason = resolve(group, build_evidence(cue), config)
    assert verdict is None
    assert reason is None


def test_resolve_falls_back_to_the_llm_when_no_rule_matches(
    tmp_path: Path, fake_llm_server
) -> None:
    path = tmp_path / "mystery.xyz123"
    path.write_bytes(b"\x01\x02\x03")
    content = json.dumps(
        {
            "kind": "router manual",
            "category": "Documents",
            "name": "a-mystery-file",
            "confidence": 0.8,
            "reason": "looks like a document",
        }
    )
    fake_llm_server.set_ollama_reply(content)

    config = _llm_config(fake_llm_server.base_url)
    verdict, reason = resolve(FileItem(path), build_evidence(path), config)
    assert reason is None
    assert verdict.category == "Documents"
    assert verdict.confidence == 0.8
    assert verdict.source == "llm"


def test_resolve_holds_with_the_llm_error_when_unreachable(tmp_path: Path) -> None:
    path = tmp_path / "mystery.xyz123"
    path.write_bytes(b"\x01\x02\x03")

    config = _llm_config("http://127.0.0.1:1")
    verdict, reason = resolve(FileItem(path), build_evidence(path), config)
    assert verdict is None
    assert reason is not None
    assert "unreachable" in reason
