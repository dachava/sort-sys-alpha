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


def test_disc_dump_without_identifiable_console_is_unsure(tmp_path: Path) -> None:
    root = tmp_path / "MyGame"
    root.mkdir()
    (root / "disc.bin").write_bytes(b"\x00" * 100)

    result = classify_subfolder(root, Config())
    assert result.verdict == "unsure"


def test_single_type_folder_of_images_is_a_unit(tmp_path: Path) -> None:
    from fixtures.make import make_png

    root = tmp_path / "Photos"
    root.mkdir()
    make_png(root / "a.png")
    make_png(root / "b.png")

    result = classify_subfolder(root, Config())
    assert result.verdict == "unit"
    assert result.category == "Images"


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


def test_process_subfolder_unsure_is_held_whole(tmp_path: Path) -> None:
    root = tmp_path / "MyGame"
    root.mkdir()
    (root / "disc.bin").write_bytes(b"\x00" * 10)

    items, held, grab_bags = process_subfolder(root, Config())
    assert items == []
    assert held == [(root, "disc/game dump, console not determined")]
