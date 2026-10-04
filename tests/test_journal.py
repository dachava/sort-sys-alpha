from pathlib import Path

from sort_sys_alpha.config import Config
from sort_sys_alpha.journal import append_entry, last_run_id, read_entries, undo_run


def _config(tmp_path: Path) -> Config:
    return Config.model_validate({"dest": str(tmp_path / "_Filed")})


def test_append_and_read(tmp_path: Path) -> None:
    config = _config(tmp_path)
    append_entry(tmp_path / "a.txt", tmp_path / "_Filed" / "a.txt", "run1", config)
    append_entry(tmp_path / "b.txt", tmp_path / "_Filed" / "b.txt", "run1", config)

    entries = read_entries(config)
    assert len(entries) == 2
    assert entries[0].run_id == "run1"


def test_last_run_id(tmp_path: Path) -> None:
    config = _config(tmp_path)
    assert last_run_id(config) is None

    append_entry(tmp_path / "a.txt", tmp_path / "_Filed" / "a.txt", "run1", config)
    append_entry(tmp_path / "b.txt", tmp_path / "_Filed" / "b.txt", "run2", config)
    assert last_run_id(config) == "run2"


def test_undo_restores_a_moved_file(tmp_path: Path) -> None:
    config = _config(tmp_path)
    source = tmp_path / "a.txt"
    target = tmp_path / "_Filed" / "Documents" / "a.txt"
    target.parent.mkdir(parents=True)
    target.write_text("hello")
    append_entry(source, target, "run1", config)

    messages = undo_run("run1", config)
    assert source.read_text() == "hello"
    assert not target.exists()
    assert "restored" in messages[0]


def test_undo_skips_if_source_already_exists(tmp_path: Path) -> None:
    config = _config(tmp_path)
    source = tmp_path / "a.txt"
    source.write_text("current")
    target = tmp_path / "_Filed" / "Documents" / "a.txt"
    target.parent.mkdir(parents=True)
    target.write_text("filed")
    append_entry(source, target, "run1", config)

    messages = undo_run("run1", config)
    assert source.read_text() == "current"
    assert target.exists()
    assert "already exists" in messages[0]


def test_undo_skips_if_target_already_gone(tmp_path: Path) -> None:
    config = _config(tmp_path)
    source = tmp_path / "a.txt"
    target = tmp_path / "_Filed" / "Documents" / "a.txt"
    append_entry(source, target, "run1", config)

    messages = undo_run("run1", config)
    assert "no longer exists" in messages[0]


def test_undo_reverses_in_most_recent_first_order(tmp_path: Path) -> None:
    config = _config(tmp_path)
    t1 = tmp_path / "_Filed" / "a.txt"
    t2 = tmp_path / "_Filed" / "b.txt"
    t1.parent.mkdir(parents=True)
    t1.write_text("a")
    t2.write_text("b")
    append_entry(tmp_path / "a.txt", t1, "run1", config)
    append_entry(tmp_path / "b.txt", t2, "run1", config)

    messages = undo_run("run1", config)
    assert "b.txt" in messages[0]
    assert "a.txt" in messages[1]
