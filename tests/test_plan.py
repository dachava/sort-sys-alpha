import json
from pathlib import Path

from sort_sys_alpha.config import Config
from sort_sys_alpha.feedback import read_routing_entries
from sort_sys_alpha.plan import build_plan, build_rename_plan, load_plan, render_report, write_plan
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


def test_build_plan_holds_with_model_unreachable_reason(tmp_path: Path) -> None:
    config = _config(tmp_path)  # default backend/base_url, nothing listening
    (config.source / "mystery.xyz123").write_bytes(b"\x01\x02\x03")

    the_plan = build_plan(config)
    assert len(the_plan.holds) == 1
    assert "unreachable" in the_plan.holds[0].reason


def test_build_plan_routes_a_rule_miss_through_the_llm(tmp_path: Path, fake_llm_server) -> None:
    config = _config(
        tmp_path,
        model={"backend": "ollama", "ollama": {"base_url": fake_llm_server.base_url}},
    )
    (config.source / "mystery.xyz123").write_bytes(b"\x01\x02\x03")
    fake_llm_server.set_ollama_reply(
        json.dumps(
            {
                "kind": "router manual",
                "category": "Documents",
                "name": "a-mystery-file",
                "confidence": 0.9,
                "reason": "looks like a document",
                "suggest_delete": True,
            }
        )
    )

    the_plan = build_plan(config)
    assert len(the_plan.moves) == 1
    move = the_plan.moves[0]
    assert move.category == "Documents"
    assert move.suggest_delete is True

    report = render_report(the_plan)
    assert "model suggests deleting" in report

    entries = read_routing_entries(config)
    assert len(entries) == 1
    assert entries[0].outcome == "moved"
    assert entries[0].category == "Documents"


def test_build_plan_records_a_held_llm_verdict_in_routing_log(
    tmp_path: Path, fake_llm_server
) -> None:
    config = _config(
        tmp_path,
        model={"backend": "ollama", "ollama": {"base_url": fake_llm_server.base_url}},
        confidence_min=0.95,
    )
    (config.source / "mystery.xyz123").write_bytes(b"\x01\x02\x03")
    fake_llm_server.set_ollama_reply(
        json.dumps(
            {
                "kind": "router manual",
                "category": "Documents",
                "name": "a-mystery-file",
                "confidence": 0.5,
                "reason": "not sure",
            }
        )
    )

    build_plan(config)

    entries = read_routing_entries(config)
    assert len(entries) == 1
    assert entries[0].outcome == "held"


def test_build_plan_holds_an_llm_routed_duplicate_of_an_already_filed_file(
    tmp_path: Path, fake_llm_server
) -> None:
    config = _config(
        tmp_path,
        model={"backend": "ollama", "ollama": {"base_url": fake_llm_server.base_url}},
    )
    existing = config.dest / "Documents" / "2026-01-01_already-filed.xyz123"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"\x01\x02\x03")

    (config.source / "mystery.xyz123").write_bytes(b"\x01\x02\x03")  # same content, redownloaded
    fake_llm_server.set_ollama_reply(
        json.dumps(
            {
                "kind": "router manual",
                "category": "Documents",
                "name": "a-mystery-file",
                "confidence": 0.9,
                "reason": "looks like a document",
            }
        )
    )

    the_plan = build_plan(config)
    assert the_plan.moves == []
    assert len(the_plan.holds) == 1
    assert f"exact duplicate of {existing}" in the_plan.holds[0].reason

    entries = read_routing_entries(config)
    assert len(entries) == 1
    assert entries[0].outcome == "held"


def test_build_plan_reports_progress_per_item(tmp_path: Path) -> None:
    config = _config(tmp_path)
    (config.source / "notes.txt").write_text("hi")
    (config.source / "mystery.xyz123").write_bytes(b"\x01\x02\x03")

    calls: list[tuple[int, int, str]] = []
    build_plan(config, on_item=lambda i, total, label: calls.append((i, total, label)))

    assert len(calls) == 2
    assert {c[2] for c in calls} == {"notes.txt", "mystery.xyz123"}
    assert all(total == 2 for _i, total, _label in calls)
    assert [c[0] for c in calls] == [1, 2]


def test_build_plan_reports_elapsed_time_per_item(tmp_path: Path) -> None:
    config = _config(tmp_path)
    (config.source / "notes.txt").write_text("hi")

    calls: list[tuple[int, int, str, float]] = []

    def _on_resolved(i: int, total: int, label: str, elapsed: float) -> None:
        calls.append((i, total, label, elapsed))

    build_plan(config, on_resolved=_on_resolved)

    assert len(calls) == 1
    index, total, label, elapsed = calls[0]
    assert (index, total, label) == (1, 1, "notes.txt")
    assert elapsed >= 0.0


def test_build_plan_records_latency_for_an_llm_verdict(tmp_path: Path, fake_llm_server) -> None:
    config = _config(
        tmp_path,
        model={"backend": "ollama", "ollama": {"base_url": fake_llm_server.base_url}},
    )
    (config.source / "mystery.xyz123").write_bytes(b"\x01\x02\x03")
    fake_llm_server.set_ollama_reply(
        json.dumps(
            {
                "kind": "router manual",
                "category": "Documents",
                "name": "a-mystery-file",
                "confidence": 0.9,
                "reason": "looks like a document",
            }
        )
    )

    build_plan(config)

    entries = read_routing_entries(config)
    assert len(entries) == 1
    assert entries[0].latency_s is not None
    assert entries[0].latency_s >= 0.0


def test_build_plan_holds_exact_duplicates_without_touching_the_llm(tmp_path: Path) -> None:
    config = _config(tmp_path)
    (config.source / "notes.txt").write_text("same content")
    (config.source / "copy of notes.txt").write_text("same content")

    the_plan = build_plan(config)
    assert len(the_plan.moves) == 1
    assert len(the_plan.holds) == 1
    assert "exact duplicate" in the_plan.holds[0].reason


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


def test_write_plan_handles_non_cp1252_filenames(tmp_path: Path) -> None:
    # Regression: write_plan() used to call Path.write_text() with no
    # encoding, which falls back to the OS locale encoding -- cp1252 on
    # Windows. A filename with a character outside cp1252 (e.g. "★", not in
    # that codepage) would crash plan.json/report.md writing with a
    # UnicodeEncodeError, even though the move itself never touches the file.
    config = _config(tmp_path)
    (config.source / "★starred-notes.txt").write_text("not in cp1252")

    the_plan = build_plan(config)
    plan_path, report_path = write_plan(the_plan, config)

    assert "★starred-notes.txt" in report_path.read_text(encoding="utf-8")
    reloaded = load_plan(plan_path)
    assert reloaded.moves[0].sources[0].name == "★starred-notes.txt"


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


def test_build_rename_plan_recovers_real_title_from_content(tmp_path: Path) -> None:
    from fixtures.make import make_docx

    config = _config(tmp_path)
    docs_dir = config.dest / "Documents"
    docs_dir.mkdir(parents=True)
    make_docx(docs_dir / "2026-01-01_old-slug-name.docx", title="Quarterly Report")

    the_plan = build_rename_plan(config)
    assert len(the_plan.moves) == 1
    move = the_plan.moves[0]
    assert move.target == docs_dir / "Quarterly Report.docx"
    assert the_plan.holds == []


def test_build_rename_plan_holds_instead_of_recategorizing(tmp_path: Path) -> None:
    config = _config(tmp_path)
    # A .nes ROM sitting in the wrong folder -- fresh identification would
    # say ROMs/nes, but it's currently filed under Documents.
    docs_dir = config.dest / "Documents"
    docs_dir.mkdir(parents=True)
    (docs_dir / "mystery.nes").write_bytes(b"NES\x1a" + b"\x00" * 50)

    the_plan = build_rename_plan(config)
    assert the_plan.moves == []
    assert len(the_plan.holds) == 1
    assert "ROMs/nes" in the_plan.holds[0].reason
    assert "re-triage" in the_plan.holds[0].reason


def test_build_rename_plan_skips_a_name_that_already_matches(tmp_path: Path) -> None:
    config = _config(tmp_path)
    docs_dir = config.dest / "Documents" / "Notes"
    docs_dir.mkdir(parents=True)
    (docs_dir / "Shopping List.txt").write_text("milk, eggs")

    the_plan = build_rename_plan(config)
    assert the_plan.moves == []
    assert the_plan.holds == []


def test_build_rename_plan_respects_path_scope(tmp_path: Path) -> None:
    from fixtures.make import make_docx

    config = _config(tmp_path)
    docs_dir = config.dest / "Documents"
    images_dir = config.dest / "Images"
    docs_dir.mkdir(parents=True)
    images_dir.mkdir(parents=True)
    make_docx(docs_dir / "2026-01-01_old-slug.docx", title="Real Title")
    (images_dir / "2026-01-01_old-photo-slug.jpg").write_bytes(b"\x00")

    the_plan = build_rename_plan(config, path=docs_dir)
    renamed = {move.move_root.name for move in the_plan.moves}
    assert renamed == {"2026-01-01_old-slug.docx"}


def test_build_rename_plan_holds_both_sides_of_an_existing_duplicate_pair(
    tmp_path: Path,
) -> None:
    """Two already-filed files that happen to be byte-identical get held
    on *both* sides, not just one -- the ADR 0009 check runs per file, and
    each one finds the other sitting in the same folder. Not destructive
    (nothing moves or is deleted), just an honest "something's off here,
    not touching either" rather than silently picking one as the winner.
    """
    config = _config(tmp_path)
    archives_dir = config.dest / "Archives"
    archives_dir.mkdir(parents=True)
    (archives_dir / "Game (USA).zip").write_bytes(b"same content")
    (archives_dir / "2026-01-01_old-slug.zip").write_bytes(b"same content")

    the_plan = build_rename_plan(config)
    assert the_plan.moves == []
    assert len(the_plan.holds) == 2
    assert all("exact duplicate" in hold.reason for hold in the_plan.holds)
