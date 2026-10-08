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


def test_fds_header_verified_routes_to_console_folder(tmp_path: Path) -> None:
    path = tmp_path / "game.fds"
    path.write_bytes(b"FDS\x1a" + b"\x00" * 50)
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "ROMs/fds"


def test_fds_without_signature_is_not_routed(tmp_path: Path) -> None:
    path = tmp_path / "fake.fds"
    path.write_bytes(b"\x00" * 50)
    assert route(build_evidence(path), Config()) is None


def test_game_gear_header_verified_routes_to_console_folder(tmp_path: Path) -> None:
    path = tmp_path / "game.gg"
    data = bytearray(0x8000)
    data[0x7FF0:0x7FF8] = b"TMR SEGA"
    path.write_bytes(bytes(data))
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "ROMs/gamegear"


def test_sega_32x_header_verified_routes_to_console_folder(tmp_path: Path) -> None:
    path = tmp_path / "game.32x"
    data = bytearray(600)
    data[0x100:0x108] = b"SEGA 32X"
    path.write_bytes(bytes(data))
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "ROMs/sega32x"


def test_sms_without_header_is_not_routed(tmp_path: Path) -> None:
    path = tmp_path / "fake.sms"
    path.write_bytes(b"\x00" * 0x8000)
    assert route(build_evidence(path), Config()) is None


def test_sg1000_extension_only_still_routes(tmp_path: Path) -> None:
    path = tmp_path / "game.sg"
    path.write_bytes(b"\x00" * 50)
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "ROMs/sg1000"


def test_extension_only_console_still_routes(tmp_path: Path) -> None:
    path = tmp_path / "game.sfc"
    path.write_bytes(b"\x00" * 50)
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "ROMs/snes"


def test_unverified_genesis_md_falls_back_to_note(tmp_path: Path) -> None:
    """.md doubles as a Markdown extension and a Genesis ROM extension;
    RomExtractor claims it first, but without the SEGA header it's almost
    certainly just a Markdown file, not a genuine (if corrupt) ROM.
    """
    path = tmp_path / "networking.md"
    path.write_text("# Networking\n\nSome docs about ports and VLANs.\n")
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "Documents/Notes"
    assert verdict.confidence == 1.0


def test_verified_genesis_rom_with_md_extension_still_routes(tmp_path: Path) -> None:
    path = tmp_path / "game.md"
    rom = bytearray(0x200)
    rom[0x100:0x104] = b"SEGA"
    path.write_bytes(bytes(rom))
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "ROMs/genesis"


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


def test_ps2_disc_with_dat_match_uses_canonical_title(tmp_path: Path) -> None:
    from fixtures.make import make_iso9660

    dat_path = tmp_path / "ps2.dat"
    dat_path.write_text(
        'game (\n  name ".Hack - Infection (USA)"\n  serial "SLUS-20267"\n'
        '  rom (\n    serial "SLUS-20267"\n    name ".Hack - Infection (USA).cue"\n  )\n)\n'
    )
    path = tmp_path / "game.iso"
    system_cnf = b"BOOT2 = cdrom0:\\SLUS_202.67;1\r\n"
    make_iso9660(path, volume_id="HACK", root_files={"SYSTEM.CNF": system_cnf})

    config = Config.model_validate({"roms": {"dat_files": {"ps2": str(dat_path)}}})
    verdict = route(build_evidence(path), config)
    assert verdict.category == "ROMs/ps2"
    assert verdict.name_hint == ".Hack - Infection (USA)"


def test_snes_rom_with_dat_match_uses_canonical_title(tmp_path: Path) -> None:
    import zlib

    data = b"\x00" * 100
    crc_hex = f"{zlib.crc32(data) & 0xFFFFFFFF:08X}"
    dat_path = tmp_path / "snes.dat"
    dat_path.write_text(f'game (\n  comment "Test Game (USA)"\n  rom ( crc {crc_hex} )\n)\n')

    path = tmp_path / "game.sfc"
    path.write_bytes(data)

    config = Config.model_validate({"roms": {"dat_files": {"snes": str(dat_path)}}})
    verdict = route(build_evidence(path), config)
    assert verdict.category == "ROMs/snes"
    assert verdict.name_hint == "Test Game (USA)"


def test_snes_rom_with_no_dat_match_has_no_name_hint(tmp_path: Path) -> None:
    dat_path = tmp_path / "snes.dat"
    dat_path.write_text('game (\n  comment "Other Game"\n  rom ( crc DEADBEEF )\n)\n')

    path = tmp_path / "game.sfc"
    path.write_bytes(b"\x00" * 100)

    config = Config.model_validate({"roms": {"dat_files": {"snes": str(dat_path)}}})
    verdict = route(build_evidence(path), config)
    assert verdict.category == "ROMs/snes"
    assert verdict.name_hint is None


def test_ps2_disc_with_no_dat_match_falls_back_to_volume_label(tmp_path: Path) -> None:
    from fixtures.make import make_iso9660

    dat_path = tmp_path / "ps2.dat"
    dat_path.write_text('game (\n  name "Other Game"\n  serial "SLUS-99999"\n)\n')
    path = tmp_path / "game.iso"
    system_cnf = b"BOOT2 = cdrom0:\\SLUS_202.67;1\r\n"
    make_iso9660(path, volume_id="HACK_VOL", root_files={"SYSTEM.CNF": system_cnf})

    config = Config.model_validate({"roms": {"dat_files": {"ps2": str(dat_path)}}})
    verdict = route(build_evidence(path), config)
    assert verdict.name_hint == "HACK_VOL"


def test_archive_routes_to_archives(tmp_path: Path) -> None:
    from fixtures.make import make_zip

    path = tmp_path / "stuff.zip"
    make_zip(path, {"a.txt": b"hi"})
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "Archives"


def test_zip_of_single_console_roms_routes_to_console_folder(tmp_path: Path) -> None:
    from fixtures.make import make_zip

    path = tmp_path / "snes-collection.zip"
    make_zip(path, {"Chrono Trigger.sfc": b"\x00" * 10, "Earthbound.sfc": b"\x00" * 10})
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "ROMs/snes"


def test_zip_ignores_incidental_non_rom_members(tmp_path: Path) -> None:
    from fixtures.make import make_zip

    path = tmp_path / "snes-game.zip"
    make_zip(path, {"game.sfc": b"\x00" * 10, "readme.txt": b"hi", "boxart.jpg": b"\xff\xd8"})
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "ROMs/snes"


def test_zip_with_only_readme_md_stays_archive(tmp_path: Path) -> None:
    from fixtures.make import make_zip

    path = tmp_path / "some-tool-main.zip"
    make_zip(path, {"README.md": b"# some-tool\n\nJust a utility, not a ROM.\n"})
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "Archives"


def test_zip_with_header_verified_genesis_md_routes_to_console(tmp_path: Path) -> None:
    from fixtures.make import make_zip

    rom = bytearray(0x200)
    rom[0x100:0x104] = b"SEGA"
    path = tmp_path / "game.zip"
    make_zip(path, {"game.md": bytes(rom)})
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "ROMs/genesis"


def test_7z_of_single_console_roms_routes_to_console_folder(tmp_path: Path) -> None:
    from fixtures.make import make_7z

    path = tmp_path / "offroad.7z"
    make_7z(path, {"Test Drive Off-Road 2 (USA).gen": b"\x00" * 10, "readme.txt": b"hi"})
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "ROMs/genesis"


def test_msx_zip_with_name_hint_routes_to_console_folder(tmp_path: Path) -> None:
    from fixtures.make import make_zip

    path = tmp_path / "Some Game (MSX).zip"
    make_zip(path, {"game.rom": b"\x00" * 10, "readme.txt": b"hi"})
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "ROMs/msx"


def test_rom_extension_zip_without_msx_name_hint_stays_archive(tmp_path: Path) -> None:
    from fixtures.make import make_zip

    path = tmp_path / "firmware-dump.zip"
    make_zip(path, {"firmware.rom": b"\x00" * 10})
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "Archives"


def test_loose_rom_extension_file_is_not_routed(tmp_path: Path) -> None:
    path = tmp_path / "Some Game (MSX).rom"
    path.write_bytes(b"\x00" * 100)
    assert route(build_evidence(path), Config()) is None


def test_zip_of_mixed_consoles_stays_archive(tmp_path: Path) -> None:
    from fixtures.make import make_zip

    path = tmp_path / "mixed.zip"
    make_zip(path, {"game.sfc": b"\x00" * 10, "other.nes": b"\x00" * 10})
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "Archives"


def test_zip_with_no_rom_members_stays_archive(tmp_path: Path) -> None:
    from fixtures.make import make_zip

    path = tmp_path / "docs.zip"
    make_zip(path, {"readme.txt": b"hi", "manual.pdf": b"%PDF-"})
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "Archives"


def test_zip_of_psx_bin_routes_to_roms_psx(tmp_path: Path) -> None:
    from fixtures.make import _build_raw_cd_bin, make_zip

    system_cnf = b"BOOT = cdrom:\\SCUS_123.45;1\r\n"
    raw = _build_raw_cd_bin("GAME", {"SYSTEM.CNF": system_cnf}, mode=2)

    path = tmp_path / "crash-bandicoot.zip"
    make_zip(path, {"Crash Bandicoot.bin": raw, "Crash Bandicoot.cue": b"junk"})
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "ROMs/psx"


def test_zip_of_saturn_bin_routes_to_roms_saturn(tmp_path: Path) -> None:
    from fixtures.make import _wrap_raw_sectors, make_zip

    cooked = bytearray(2048)
    cooked[: len(b"SEGA SEGASATURN")] = b"SEGA SEGASATURN"
    raw = _wrap_raw_sectors(bytes(cooked), mode=1)

    path = tmp_path / "panzer-dragoon.zip"
    make_zip(path, {"Panzer Dragoon.bin": raw, "Panzer Dragoon.cue": b"junk"})
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "ROMs/saturn"


def test_zip_of_generic_iso_disc_stays_archive(tmp_path: Path) -> None:
    from fixtures.make import _build_iso9660_image, make_zip

    cooked = _build_iso9660_image("LINUX", None)
    path = tmp_path / "linux-live.zip"
    make_zip(path, {"linux.iso": cooked})
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


def test_dol_routes_to_roms_wii(tmp_path: Path) -> None:
    path = tmp_path / "homebrew.dol"
    path.write_bytes(b"\x00" * 50)
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "ROMs/wii"


def test_rvz_routes_to_isos(tmp_path: Path) -> None:
    from fixtures.make import make_disc_magic

    path = tmp_path / "game.rvz"
    make_disc_magic(path, offset=0x0, magic=b"RVZ\x01")
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "ISOs"


def test_ips_patch_routes_to_other(tmp_path: Path) -> None:
    path = tmp_path / "translation.ips"
    path.write_bytes(b"PATCH" + b"\x00" * 10)
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "Other"


def test_url_shortcut_routes_to_documents(tmp_path: Path) -> None:
    path = tmp_path / "saved.url"
    path.write_text("[InternetShortcut]\nURL=https://example.com\n")
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "Documents"


def test_safetensors_routes_to_other(tmp_path: Path) -> None:
    header_json = b'{"__metadata__":{}}'
    path = tmp_path / "model.safetensors"
    path.write_bytes(len(header_json).to_bytes(8, "little") + header_json + b"\x00" * 5)
    verdict = route(build_evidence(path), Config())
    assert verdict.category == "Other"


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


def test_resolve_folder_unit_propagates_suggest_delete(tmp_path: Path) -> None:
    root = tmp_path / "options"
    root.mkdir()
    (root / "a.rc").write_bytes(b"\x00")
    unit = FolderUnit(root, "Other", "single-type folder", (root / "a.rc",), suggest_delete=True)

    verdict, _reason = resolve(unit, build_evidence(root), Config())
    assert verdict.suggest_delete is True


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
