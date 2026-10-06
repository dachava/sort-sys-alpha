from pathlib import Path

from sort_sys_alpha.config import Config
from sort_sys_alpha.prune import prune_empty_folders


def _config(source: Path) -> Config:
    return Config.model_validate({"source": str(source), "dest": str(source / "_Filed")})


def test_removes_a_lone_empty_folder(tmp_path: Path) -> None:
    source = tmp_path / "Downloads"
    (source / "Empty").mkdir(parents=True)

    result = prune_empty_folders(_config(source))
    assert result.removed == [source / "Empty"]
    assert not (source / "Empty").exists()


def test_removes_nested_structure_with_no_files_at_any_level(tmp_path: Path) -> None:
    source = tmp_path / "Downloads"
    (source / "Outer" / "Inner" / "Deeper").mkdir(parents=True)

    result = prune_empty_folders(_config(source))
    assert not (source / "Outer").exists()
    assert len(result.removed) == 3


def test_keeps_a_folder_with_a_file_at_any_depth(tmp_path: Path) -> None:
    source = tmp_path / "Downloads"
    (source / "Outer" / "Inner").mkdir(parents=True)
    (source / "Outer" / "Inner" / "keep.txt").write_text("hi")

    result = prune_empty_folders(_config(source))
    assert result.removed == []
    assert (source / "Outer" / "Inner" / "keep.txt").exists()


def test_a_sibling_file_keeps_only_its_own_branch(tmp_path: Path) -> None:
    source = tmp_path / "Downloads"
    (source / "Outer" / "HasFile").mkdir(parents=True)
    (source / "Outer" / "Empty").mkdir(parents=True)
    (source / "Outer" / "HasFile" / "keep.txt").write_text("hi")

    result = prune_empty_folders(_config(source))
    assert result.removed == [source / "Outer" / "Empty"]
    assert (source / "Outer").exists()
    assert (source / "Outer" / "HasFile" / "keep.txt").exists()


def test_never_touches_dest(tmp_path: Path) -> None:
    source = tmp_path / "Downloads"
    dest = source / "_Filed"
    dest.mkdir(parents=True)

    result = prune_empty_folders(_config(source))
    assert result.removed == []
    assert dest.exists()


def test_never_touches_hidden_folders(tmp_path: Path) -> None:
    source = tmp_path / "Downloads"
    (source / ".git").mkdir(parents=True)

    result = prune_empty_folders(_config(source))
    assert result.removed == []
    assert (source / ".git").exists()


def test_hidden_folder_blocks_its_ancestor_from_removal(tmp_path: Path) -> None:
    source = tmp_path / "Downloads"
    (source / "Outer" / ".git").mkdir(parents=True)

    result = prune_empty_folders(_config(source))
    assert result.removed == []
    assert (source / "Outer").exists()


def test_no_empty_folders_is_a_no_op(tmp_path: Path) -> None:
    source = tmp_path / "Downloads"
    source.mkdir()
    (source / "notes.txt").write_text("hi")

    result = prune_empty_folders(_config(source))
    assert result.removed == []
