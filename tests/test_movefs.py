from pathlib import Path

import pytest

from sort_sys_alpha.movefs import (
    MoveVerificationError,
    hash_file,
    hash_tree,
    move_path,
    unique_target,
)


def test_unique_target_returns_same_path_if_free(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    assert unique_target(target) == target


def test_unique_target_suffixes_on_collision(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_text("existing")
    assert unique_target(target) == tmp_path / "file-2.txt"

    (tmp_path / "file-2.txt").write_text("also existing")
    assert unique_target(target) == tmp_path / "file-3.txt"


def test_move_file_same_volume(tmp_path: Path) -> None:
    source = tmp_path / "a.txt"
    source.write_text("hello")
    target = tmp_path / "sub" / "a.txt"

    move_path(source, target)
    assert not source.exists()
    assert target.read_text() == "hello"


def test_move_directory(tmp_path: Path) -> None:
    source = tmp_path / "folder"
    source.mkdir()
    (source / "a.txt").write_text("hello")
    (source / "nested").mkdir()
    (source / "nested" / "b.txt").write_text("world")
    target = tmp_path / "dest" / "folder"

    move_path(source, target)
    assert not source.exists()
    assert (target / "a.txt").read_text() == "hello"
    assert (target / "nested" / "b.txt").read_text() == "world"


def test_hash_file_is_content_dependent(tmp_path: Path) -> None:
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("hello")
    b.write_text("world")
    assert hash_file(a) != hash_file(b)
    b.write_text("hello")
    assert hash_file(a) == hash_file(b)


def test_hash_tree_depends_on_relative_structure(tmp_path: Path) -> None:
    root1 = tmp_path / "t1"
    root1.mkdir()
    (root1 / "x.txt").write_text("hi")
    root2 = tmp_path / "t2"
    root2.mkdir()
    (root2 / "x.txt").write_text("hi")
    assert hash_tree(root1) == hash_tree(root2)

    (root2 / "y.txt").write_text("extra")
    assert hash_tree(root1) != hash_tree(root2)


def test_move_verification_error_on_corrupted_copy(tmp_path: Path, monkeypatch) -> None:
    import shutil

    source = tmp_path / "a.txt"
    source.write_text("hello")
    target = tmp_path / "b.txt"

    # Force the cross-volume fallback path, then corrupt the copy to
    # trigger the hash-mismatch guard.
    monkeypatch.setattr(Path, "rename", lambda self, _t: (_ for _ in ()).throw(OSError("exdev")))

    def _bad_copy(src, dst):
        Path(dst).write_text("corrupted")

    monkeypatch.setattr(shutil, "copy2", _bad_copy)

    with pytest.raises(MoveVerificationError):
        move_path(source, target)
