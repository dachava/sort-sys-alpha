import time
from pathlib import Path

from sort_sys_alpha.config import Config
from sort_sys_alpha.items import FileItem
from sort_sys_alpha.scan import SkippedItem, scan


def _config(tmp_path: Path, **overrides) -> Config:
    source = tmp_path / "Downloads"
    source.mkdir(exist_ok=True)
    data = {"source": str(source), "dest": str(source / "_Filed"), "min_age_minutes": 0}
    data.update(overrides)
    return Config.model_validate(data)


def _age(path: Path, minutes_ago: float) -> None:
    ts = time.time() - minutes_ago * 60
    import os

    os.utime(path, (ts, ts))


def test_picks_up_a_plain_file(tmp_path: Path) -> None:
    config = _config(tmp_path)
    (config.source / "notes.txt").write_text("hi")

    result = scan(config)
    assert result.items == [FileItem(path=config.source / "notes.txt")]
    assert result.skipped == []


def test_skips_partial_downloads(tmp_path: Path) -> None:
    config = _config(tmp_path)
    (config.source / "movie.mp4.crdownload").write_bytes(b"\x00")

    result = scan(config)
    partial = config.source / "movie.mp4.crdownload"
    assert result.items == []
    assert result.skipped == [SkippedItem(partial, "partial download")]


def test_skips_recently_modified_files(tmp_path: Path) -> None:
    config = _config(tmp_path, min_age_minutes=30)
    path = config.source / "fresh.txt"
    path.write_text("hi")
    _age(path, minutes_ago=1)

    result = scan(config)
    assert result.items == []
    assert result.skipped == [SkippedItem(path, "modified too recently")]


def test_old_enough_file_is_picked_up(tmp_path: Path) -> None:
    config = _config(tmp_path, min_age_minutes=30)
    path = config.source / "old.txt"
    path.write_text("hi")
    _age(path, minutes_ago=60)

    result = scan(config)
    assert result.items == [FileItem(path=path)]


def test_skips_hidden_files(tmp_path: Path) -> None:
    config = _config(tmp_path)
    (config.source / ".DS_Store").write_bytes(b"\x00")

    result = scan(config)
    assert result.items == []
    assert result.skipped[0].reason == "hidden file"


def test_subfolders_are_held_not_descended_into(tmp_path: Path) -> None:
    config = _config(tmp_path)
    sub = config.source / "extracted_app"
    sub.mkdir()
    (sub / "setup.exe").write_bytes(b"\x00")

    result = scan(config)
    assert result.items == []
    assert result.skipped == [SkippedItem(sub, "subfolder (handled in a later milestone)")]


def test_dest_folder_itself_is_never_scanned(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.dest.mkdir(parents=True)
    (config.dest / "already_filed.txt").write_text("hi")

    result = scan(config)
    assert result.items == []
    assert result.skipped == []


def test_groups_are_detected_across_top_level_files(tmp_path: Path) -> None:
    config = _config(tmp_path)
    (config.source / "game.cue").write_text('FILE "game.bin" BINARY\n')
    (config.source / "game.bin").write_bytes(b"\x00" * 10)

    result = scan(config)
    assert len(result.items) == 1
    assert result.items[0].kind == "cue_bin"
