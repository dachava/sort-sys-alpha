from pathlib import Path

from sort_sys_alpha.groups import detect_groups
from sort_sys_alpha.identify import identify_item
from sort_sys_alpha.items import FileGroup, FileItem


def _names(items, kind: str) -> list[str]:
    for item in items:
        if isinstance(item, FileGroup) and item.kind == kind:
            return [m.name for m in item.members]
    raise AssertionError(f"no {kind} group found among {items}")


def test_cue_bin_group(tmp_path: Path) -> None:
    (tmp_path / "game.cue").write_text('FILE "game.bin" BINARY\n  TRACK 01 MODE2/2352\n')
    (tmp_path / "game.bin").write_bytes(b"\x00" * 100)

    items = detect_groups(sorted(tmp_path.iterdir()))
    assert _names(items, "cue_bin") == ["game.cue", "game.bin"]


def test_gdi_group_with_quoted_filenames(tmp_path: Path) -> None:
    (tmp_path / "disc.gdi").write_text(
        '2\n1 0 4 2048 "track01.bin" 0\n2 150 0 2352 "track02.raw" 0\n'
    )
    (tmp_path / "track01.bin").write_bytes(b"\x00" * 50)
    (tmp_path / "track02.raw").write_bytes(b"\x00" * 50)

    items = detect_groups(sorted(tmp_path.iterdir()))
    assert _names(items, "gdi") == ["disc.gdi", "track01.bin", "track02.raw"]


def test_m3u_group(tmp_path: Path) -> None:
    (tmp_path / "game.m3u").write_text("disc1.iso\ndisc2.iso\n")
    (tmp_path / "disc1.iso").write_bytes(b"\x00" * 10)
    (tmp_path / "disc2.iso").write_bytes(b"\x00" * 10)

    items = detect_groups(sorted(tmp_path.iterdir()))
    assert _names(items, "m3u") == ["game.m3u", "disc1.iso", "disc2.iso"]


def test_ccd_group(tmp_path: Path) -> None:
    (tmp_path / "image.ccd").write_text("dummy")
    (tmp_path / "image.img").write_bytes(b"\x00" * 10)
    (tmp_path / "image.sub").write_bytes(b"\x00" * 10)

    items = detect_groups(sorted(tmp_path.iterdir()))
    assert _names(items, "ccd") == ["image.ccd", "image.img", "image.sub"]


def test_unreferenced_files_stay_ungrouped(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("hello")

    items = detect_groups(sorted(tmp_path.iterdir()))
    assert items == [FileItem(path=tmp_path / "notes.txt")]


def test_cue_without_a_matching_bin_is_not_a_group(tmp_path: Path) -> None:
    (tmp_path / "game.cue").write_text('FILE "missing.bin" BINARY\n')

    items = detect_groups(sorted(tmp_path.iterdir()))
    assert items == [FileItem(path=tmp_path / "game.cue")]


def test_identify_item_on_a_group_reports_disc_group(tmp_path: Path) -> None:
    cue_text = 'FILE "game.bin" BINARY\n'
    # newline="" avoids Windows' text-mode \n -> \r\n translation, so the
    # on-disk size matches len(cue_text) on every OS.
    (tmp_path / "game.cue").write_text(cue_text, newline="")
    (tmp_path / "game.bin").write_bytes(b"\x00" * 100)

    items = detect_groups(sorted(tmp_path.iterdir()))
    group = next(i for i in items if isinstance(i, FileGroup))

    evidence = identify_item(group)
    assert evidence.kind == "disc_group"
    assert evidence.details["group_kind"] == "cue_bin"
    assert evidence.details["member_count"] == 2
    assert evidence.details["total_size"] == 100 + len(cue_text)


def test_identify_item_on_a_file_uses_the_normal_pipeline(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("hello")

    evidence = identify_item(FileItem(path=path))
    assert evidence.kind == "text"
