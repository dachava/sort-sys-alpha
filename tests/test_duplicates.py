from pathlib import Path

from sort_sys_alpha.duplicates import find_duplicate_in_dest, partition_duplicates
from sort_sys_alpha.items import FileGroup, FileItem, FolderUnit


def test_two_identical_files_keep_one_and_hold_the_other(tmp_path: Path) -> None:
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("same content")
    b.write_text("same content")

    remaining, holds = partition_duplicates([FileItem(a), FileItem(b)])

    assert remaining == [FileItem(a)]
    assert len(holds) == 1
    path, reason = holds[0]
    assert path == b
    assert "exact duplicate" in reason
    assert str(a) in reason


def test_same_size_different_content_are_not_duplicates(tmp_path: Path) -> None:
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("aaaaa")
    b.write_text("bbbbb")

    remaining, holds = partition_duplicates([FileItem(a), FileItem(b)])

    assert remaining == [FileItem(a), FileItem(b)]
    assert holds == []


def test_three_way_duplicate_keeps_only_the_first(tmp_path: Path) -> None:
    paths = [tmp_path / name for name in ("a.txt", "b.txt", "c.txt")]
    for path in paths:
        path.write_text("same content")

    remaining, holds = partition_duplicates([FileItem(p) for p in paths])

    assert remaining == [FileItem(paths[0])]
    assert {path for path, _reason in holds} == {paths[1], paths[2]}


def test_file_groups_and_folder_units_pass_through_untouched(tmp_path: Path) -> None:
    cue = tmp_path / "game.cue"
    bin_ = tmp_path / "game.bin"
    cue.write_text("cue sheet")
    bin_.write_bytes(b"\x00")
    group = FileGroup("cue_bin", cue, (cue, bin_))

    root = tmp_path / "App"
    root.mkdir()
    (root / "setup.exe").write_bytes(b"\x00")
    unit = FolderUnit(root, "Installers", "extracted app markers", (root / "setup.exe",))

    remaining, holds = partition_duplicates([group, unit])

    assert remaining == [group, unit]
    assert holds == []


def test_single_file_is_not_a_duplicate_of_anything(tmp_path: Path) -> None:
    path = tmp_path / "solo.txt"
    path.write_text("unique")

    remaining, holds = partition_duplicates([FileItem(path)])

    assert remaining == [FileItem(path)]
    assert holds == []


def test_find_duplicate_in_dest_matches_a_real_sibling(tmp_path: Path) -> None:
    dest_dir = tmp_path / "ROMs" / "genesis"
    dest_dir.mkdir(parents=True)
    existing = dest_dir / "game.md"
    existing.write_bytes(b"same content")

    candidate = tmp_path / "redownload.md"
    candidate.write_bytes(b"same content")

    assert find_duplicate_in_dest(candidate, dest_dir) == existing


def test_find_duplicate_in_dest_excludes_the_candidate_itself(tmp_path: Path) -> None:
    """A --source rescan of a folder already inside dest can pass a path
    that's already sitting in the very directory being searched (ADR 0009
    amendment) -- it must never match itself.
    """
    dest_dir = tmp_path / "Archives"
    dest_dir.mkdir()
    candidate = dest_dir / "mystery.zip"
    candidate.write_bytes(b"unidentified content")

    assert find_duplicate_in_dest(candidate, dest_dir) is None


def test_find_duplicate_in_dest_no_match_returns_none(tmp_path: Path) -> None:
    dest_dir = tmp_path / "Archives"
    dest_dir.mkdir()
    (dest_dir / "other.zip").write_bytes(b"different content")

    candidate = tmp_path / "new.zip"
    candidate.write_bytes(b"unique content")

    assert find_duplicate_in_dest(candidate, dest_dir) is None


def test_find_duplicate_in_dest_missing_dir_returns_none(tmp_path: Path) -> None:
    candidate = tmp_path / "new.zip"
    candidate.write_bytes(b"content")

    assert find_duplicate_in_dest(candidate, tmp_path / "does-not-exist") is None
