from pathlib import Path

from sort_sys_alpha.config import Config
from sort_sys_alpha.plan import build_plan, load_plan, render_report, write_plan
from sort_sys_alpha.scan import STATE_DIR_NAME


def _config(tmp_path: Path, **overrides) -> Config:
    source = tmp_path / "Downloads"
    source.mkdir(exist_ok=True)
    data = {"source": str(source), "dest": str(source / "_Filed"), "min_age_minutes": 0}
    data.update(overrides)
    return Config.model_validate(data)


def test_build_plan_separates_moves_and_holds(tmp_path: Path) -> None:
    config = _config(tmp_path)
    (config.source / "notes.txt").write_text("hi")
    (config.source / "mystery.xyz123").write_bytes(b"\x01\x02\x03")

    the_plan = build_plan(config)
    assert len(the_plan.moves) == 1
    assert the_plan.moves[0].category == "Documents/Notes"
    assert len(the_plan.holds) == 1


def test_build_plan_includes_scan_skips_as_holds(tmp_path: Path) -> None:
    config = _config(tmp_path)
    (config.source / "partial.crdownload").write_bytes(b"\x00")

    the_plan = build_plan(config)
    assert any("partial download" in h.reason for h in the_plan.holds)


def test_write_plan_creates_plan_report_and_held_log(tmp_path: Path) -> None:
    config = _config(tmp_path)
    (config.source / "notes.txt").write_text("hi")
    (config.source / "mystery.xyz123").write_bytes(b"\x01\x02\x03")

    the_plan = build_plan(config)
    plan_path, report_path = write_plan(the_plan, config)

    assert plan_path.exists()
    assert report_path.exists()
    assert (config.dest / STATE_DIR_NAME / "held.log").exists()
    assert "mystery.xyz123" in (config.dest / STATE_DIR_NAME / "held.log").read_text()


def test_plan_json_round_trips(tmp_path: Path) -> None:
    config = _config(tmp_path)
    (config.source / "notes.txt").write_text("hi")

    the_plan = build_plan(config)
    plan_path, _report_path = write_plan(the_plan, config)

    reloaded = load_plan(plan_path)
    assert reloaded.run_id == the_plan.run_id
    assert len(reloaded.moves) == len(the_plan.moves)
    assert reloaded.moves[0].target == the_plan.moves[0].target


def test_render_report_lists_moves_and_holds(tmp_path: Path) -> None:
    config = _config(tmp_path)
    (config.source / "notes.txt").write_text("hi")
    (config.source / "mystery.xyz123").write_bytes(b"\x01\x02\x03")

    the_plan = build_plan(config)
    report = render_report(the_plan)
    assert "## Moves (1)" in report
    assert "## Held (1)" in report
    assert "notes.txt" in report
    assert "mystery.xyz123" in report
