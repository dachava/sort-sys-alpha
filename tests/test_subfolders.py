from pathlib import Path

from sort_sys_alpha.config import Config
from sort_sys_alpha.items import FolderUnit
from sort_sys_alpha.subfolders import classify_subfolder, process_subfolder


def test_extracted_app_is_a_unit(tmp_path: Path) -> None:
    root = tmp_path / "MyApp"
    root.mkdir()
    (root / "setup.exe").write_bytes(b"\x00")
    (root / "lib.dll").write_bytes(b"\x00")

    result = classify_subfolder(root, Config())
    assert result.verdict == "unit"
    assert result.category == "Installers"


def test_portable_exe_with_batch_helpers_is_a_unit(tmp_path: Path) -> None:
    """A portable tool (chdman, ffmpeg, ...) has no installer and no .dll,
    just an .exe plus helper .bat scripts it needs to run -- that's still
    "data needed for execution" and has to move as one folder, not get
    split and leave the scripts behind with nothing to route them.
    """
    root = tmp_path / "chdman"
    root.mkdir()
    (root / "chdman.exe").write_bytes(b"\x00")
    (root / "chd2cue.bat").write_text("chdman.exe extractcd %1 %2\n")

    result = classify_subfolder(root, Config())
    assert result.verdict == "unit"
    assert result.category == "Installers"


def test_extracted_app_with_incidental_bin_is_still_a_unit(tmp_path: Path) -> None:
    """A stray `.bin` (e.g. Chromium's v8_context_snapshot.bin) shouldn't
    make an otherwise-ordinary extracted app look like an unresolved disc
    dump and get held instead of recognized as Installers.
    """
    root = tmp_path / "chrome-win"
    root.mkdir()
    (root / "chrome.exe").write_bytes(b"\x00")
    (root / "chrome_elf.dll").write_bytes(b"\x00")
    (root / "v8_context_snapshot.bin").write_bytes(b"\x00" * 100)

    result = classify_subfolder(root, Config())
    assert result.verdict == "unit"
    assert result.category == "Installers"


def test_code_project_is_a_unit_in_other(tmp_path: Path) -> None:
    root = tmp_path / "myrepo"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\n")

    result = classify_subfolder(root, Config())
    assert result.verdict == "unit"
    assert result.category == "Other"


def test_album_is_a_unit(tmp_path: Path) -> None:
    root = tmp_path / "MyAlbum"
    root.mkdir()
    (root / "track1.mp3").write_bytes(b"\x00")
    (root / "album.cue").write_text('FILE "track1.mp3" MP3')

    result = classify_subfolder(root, Config())
    assert result.verdict == "unit"
    assert result.category == "Audio"


def test_disc_dump_with_identifiable_console_is_a_unit(tmp_path: Path) -> None:
    from fixtures.make import make_iso9660

    root = tmp_path / "MyGame"
    root.mkdir()
    make_iso9660(root / "disc.iso", volume_id="GAME", root_files={"SYSTEM.CNF": b"BOOT2 = x;1\r\n"})

    result = classify_subfolder(root, Config())
    assert result.verdict == "unit"
    assert result.category == "ROMs/ps2"


def test_lone_unidentifiable_bin_is_a_grab_bag(tmp_path: Path) -> None:
    """A bare `.bin` with no disc sheet and no identifiable console isn't
    trusted as "this folder is a disc dump" on its own -- too many ordinary
    non-disc files use that extension (see DISC_SHEET_EXTENSIONS above) --
    so it falls through to grab_bag and gets processed like any other
    unidentified file, rather than holding the whole folder hostage.
    """
    root = tmp_path / "MyGame"
    root.mkdir()
    (root / "disc.bin").write_bytes(b"\x00" * 100)

    result = classify_subfolder(root, Config())
    assert result.verdict == "grab_bag"


def test_disc_sheet_without_identifiable_console_is_unsure(tmp_path: Path) -> None:
    """Unlike a bare `.bin`, a `.gdi`/`.m3u`/`.ccd` sheet has no non-disc
    use, so failing to identify its console is still a whole-folder hold.
    """
    root = tmp_path / "MyGame"
    root.mkdir()
    (root / "disc.gdi").write_text("4\n")
    (root / "track01.bin").write_bytes(b"\x00" * 100)

    result = classify_subfolder(root, Config())
    assert result.verdict == "unsure"


def test_psx_bin_cue_folder_is_a_unit(tmp_path: Path) -> None:
    from fixtures.make import _build_raw_cd_bin

    root = tmp_path / "Castlevania - Symphony of the Night (USA)"
    root.mkdir()
    system_cnf = b"BOOT = cdrom:\\SCUS_123.45;1\r\n"
    raw = _build_raw_cd_bin("SOTN", {"SYSTEM.CNF": system_cnf}, mode=2)
    (root / "Castlevania - SOTN.bin").write_bytes(raw)
    (root / "Castlevania - SOTN.cue").write_text(
        'FILE "Castlevania - SOTN.bin" BINARY\n  TRACK 01 MODE2/2352\n'
    )

    result = classify_subfolder(root, Config())
    assert result.verdict == "unit"
    assert result.category == "ROMs/psx"


def test_cartridge_rom_with_incidental_bin_splits_as_grab_bag(tmp_path: Path) -> None:
    """A genuine cartridge dump (Genesis .md, header-verified) sitting next
    to an unrelated `.bin` (a save file, a diff, whatever) isn't a single
    coherent unit -- it should split rather than get held as an unresolved
    disc dump, so the actual ROM still gets classified once split out.
    """
    root = tmp_path / "blacktiger_MD_v1.7"
    root.mkdir()
    rom = bytearray(0x200)
    rom[0x100:0x104] = b"SEGA"
    (root / "Black Tiger.md").write_bytes(bytes(rom))
    (root / "Black Tiger.bin").write_bytes(b"\x00" * 50)

    result = classify_subfolder(root, Config())
    assert result.verdict == "grab_bag"


def test_single_type_folder_of_images_is_a_unit(tmp_path: Path) -> None:
    from fixtures.make import make_png

    root = tmp_path / "Photos"
    root.mkdir()
    make_png(root / "a.png")
    make_png(root / "b.png")

    result = classify_subfolder(root, Config())
    assert result.verdict == "unit"
    assert result.category == "Images"


def _romdef(game: str) -> str:
    return f'game {game} MVS "Test {game}"\nCPU 0x200000\na.bin 0x0 0x100000 NORM\nEND\n'


def test_single_type_folder_propagates_suggest_delete(tmp_path: Path) -> None:
    root = tmp_path / "options"
    root.mkdir()
    (root / "a.rc").write_text(_romdef("a"))
    (root / "b.rc").write_text(_romdef("b"))

    result = classify_subfolder(root, Config())
    assert result.verdict == "unit"
    assert result.category == "Other"
    assert result.suggest_delete is True


def test_single_type_folder_requires_every_member_to_agree_on_suggest_delete(
    tmp_path: Path,
) -> None:
    root = tmp_path / "options"
    root.mkdir()
    (root / "a.rc").write_text(_romdef("a"))  # suggest_delete=True (mame_romdef rule)
    (root / "b.txt").write_text("hi")  # routed to "Other" too, but via a plain config rule

    config = Config.model_validate({"rules": [{"match": {"ext": [".txt"]}, "folder": "Other"}]})
    result = classify_subfolder(root, config)
    assert result.verdict == "unit"
    assert result.category == "Other"
    assert result.suggest_delete is False  # one member didn't agree, so the unit doesn't claim it


def test_mixed_folder_with_no_markers_is_grab_bag(tmp_path: Path) -> None:
    root = tmp_path / "junk"
    root.mkdir()
    (root / "a.txt").write_text("hi")
    (root / "b.jpg").write_bytes(b"\x00")

    result = classify_subfolder(root, Config())
    assert result.verdict == "grab_bag"


def test_conflicting_markers_is_unsure(tmp_path: Path) -> None:
    root = tmp_path / "weird"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\n")
    (root / "setup.exe").write_bytes(b"\x00")
    (root / "lib.dll").write_bytes(b"\x00")

    result = classify_subfolder(root, Config())
    assert result.verdict == "unsure"


def test_exceeds_file_limit_is_held_as_limit(tmp_path: Path) -> None:
    root = tmp_path / "huge"
    root.mkdir()
    for i in range(5):
        (root / f"f{i}.txt").write_text("x")
    config = Config.model_validate({"subfolders": {"max_files": 2}})

    result = classify_subfolder(root, config)
    assert result.verdict == "limit"


def test_process_subfolder_unit_returns_folder_unit_with_all_members(tmp_path: Path) -> None:
    root = tmp_path / "MyApp"
    root.mkdir()
    (root / "setup.exe").write_bytes(b"\x00")
    (root / "data").mkdir()
    (root / "data" / "config.ini").write_text("x")

    items, held, grab_bags = process_subfolder(root, Config())
    assert len(items) == 1
    unit = items[0]
    assert isinstance(unit, FolderUnit)
    assert len(unit.members) == 2
    assert held == []
    assert grab_bags == []


def test_process_subfolder_grab_bag_recurses_into_nested_units(tmp_path: Path) -> None:
    root = tmp_path / "downloads_junk"
    root.mkdir()
    (root / "loose.txt").write_text("hi")
    nested = root / "SomeApp"
    nested.mkdir()
    (nested / "setup.exe").write_bytes(b"\x00")
    (nested / "lib.dll").write_bytes(b"\x00")

    items, held, grab_bags = process_subfolder(root, Config())
    from sort_sys_alpha.items import FileItem

    kinds = {type(i) for i in items}
    assert FileItem in kinds
    assert FolderUnit in kinds
    assert grab_bags == [root]


def test_process_subfolder_unit_carries_suggest_delete(tmp_path: Path) -> None:
    root = tmp_path / "options"
    root.mkdir()
    (root / "a.rc").write_text(_romdef("a"))
    (root / "b.rc").write_text(_romdef("b"))

    items, _held, _grab_bags = process_subfolder(root, Config())
    assert len(items) == 1
    assert items[0].suggest_delete is True


def test_process_subfolder_unsure_is_held_whole(tmp_path: Path) -> None:
    root = tmp_path / "MyGame"
    root.mkdir()
    (root / "disc.gdi").write_text("4\n")
    (root / "track01.bin").write_bytes(b"\x00" * 10)

    items, held, grab_bags = process_subfolder(root, Config())
    assert items == []
    assert held == [(root, "disc/game dump, console not determined")]
