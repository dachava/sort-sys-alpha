from pathlib import Path

from sort_sys_alpha.apply import apply_plan
from sort_sys_alpha.config import Config
from sort_sys_alpha.journal import read_entries
from sort_sys_alpha.plan import build_plan


def _config(tmp_path: Path, **overrides) -> Config:
    source = tmp_path / "Downloads"
    source.mkdir(exist_ok=True)
    data = {"source": str(source), "dest": str(source / "_Filed"), "min_age_minutes": 0}
    data.update(overrides)
    return Config.model_validate(data)


def test_apply_moves_a_file_and_journals_it(tmp_path: Path) -> None:
    config = _config(tmp_path)
    (config.source / "notes.txt").write_text("hi")

    the_plan = build_plan(config)
    result = apply_plan(the_plan, config)

    assert len(result.moved) == 1
    assert not (config.source / "notes.txt").exists()
    target = config.dest / "Documents" / "Notes"
    assert any(target.iterdir())
    assert len(read_entries(config)) == 1


def test_apply_skips_a_file_that_changed_since_plan(tmp_path: Path) -> None:
    config = _config(tmp_path)
    path = config.source / "notes.txt"
    path.write_text("hi")

    the_plan = build_plan(config)
    path.write_text("changed content, different size")

    result = apply_plan(the_plan, config)
    assert result.moved == []
    assert len(result.held) == 1
    assert "changed between plan and apply" in result.held[0][1]
    assert path.exists()


def test_apply_skips_a_file_removed_since_plan(tmp_path: Path) -> None:
    config = _config(tmp_path)
    path = config.source / "notes.txt"
    path.write_text("hi")

    the_plan = build_plan(config)
    path.unlink()

    result = apply_plan(the_plan, config)
    assert result.moved == []
    assert len(result.held) == 1


def test_apply_handles_collisions_with_a_suffix(tmp_path: Path) -> None:
    config = _config(tmp_path)
    (config.source / "notes.txt").write_text("first")

    the_plan = build_plan(config)
    target = the_plan.moves[0].target
    target.parent.mkdir(parents=True)
    target.write_text("already here")

    result = apply_plan(the_plan, config)
    assert len(result.moved) == 1
    _root, final_target = result.moved[0]
    assert final_target != target
    assert final_target.read_text() == "first"
    assert target.read_text() == "already here"


def test_apply_moves_a_folder_unit_intact(tmp_path: Path) -> None:
    config = _config(tmp_path)
    app = config.source / "MyApp"
    app.mkdir()
    (app / "setup.exe").write_bytes(b"\x00")
    (app / "lib.dll").write_bytes(b"\x00")

    the_plan = build_plan(config)
    result = apply_plan(the_plan, config)

    assert len(result.moved) == 1
    assert not app.exists()
    _root, target = result.moved[0]
    assert (target / "setup.exe").exists()
    assert (target / "lib.dll").exists()


def test_apply_reports_emptied_grab_bag_folder_without_deleting(tmp_path: Path) -> None:
    config = _config(tmp_path)
    junk = config.source / "junk"
    junk.mkdir()
    (junk / "notes.txt").write_text("hi")

    the_plan = build_plan(config)
    result = apply_plan(the_plan, config)

    assert result.emptied_folders == [junk]
    assert junk.exists()
    assert not any(junk.iterdir())


def test_apply_does_not_report_a_grab_bag_folder_with_a_held_file(tmp_path: Path) -> None:
    config = _config(tmp_path)
    junk = config.source / "junk"
    junk.mkdir()
    (junk / "mystery.xyz123").write_bytes(b"\x01\x02\x03")  # unrouted -> held

    the_plan = build_plan(config)
    result = apply_plan(the_plan, config)

    assert result.emptied_folders == []
    assert any(junk.iterdir())


def test_apply_cross_volume_fallback_still_verifies_and_removes_source(
    tmp_path: Path, monkeypatch
) -> None:
    config = _config(tmp_path)
    (config.source / "notes.txt").write_text("hi")
    the_plan = build_plan(config)

    def _fail_rename(self, _target):
        raise OSError("simulated cross-device move")

    monkeypatch.setattr(Path, "rename", _fail_rename)
    result = apply_plan(the_plan, config)

    assert len(result.moved) == 1
    assert not (config.source / "notes.txt").exists()
