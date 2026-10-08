import json
from pathlib import Path

from sort_sys_alpha.apply import apply_plan
from sort_sys_alpha.config import Config
from sort_sys_alpha.feedback import read_routing_entries
from sort_sys_alpha.journal import read_entries
from sort_sys_alpha.plan import build_plan, load_plan, write_plan


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


def test_apply_records_a_correction_when_the_plan_category_was_hand_edited(
    tmp_path: Path, fake_llm_server
) -> None:
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

    the_plan = build_plan(config)
    plan_path, _report_path = write_plan(the_plan, config)

    # Simulate a human hand-editing plan.json before `apply` runs.
    data = json.loads(plan_path.read_text())
    data["moves"][0]["category"] = "Other"
    data["moves"][0]["target"] = str(config.dest / "Other" / "a-mystery-file.xyz123")
    plan_path.write_text(json.dumps(data))

    edited_plan = load_plan(plan_path)
    apply_plan(edited_plan, config)

    entries = read_routing_entries(config)
    assert len(entries) == 2
    assert entries[0].outcome == "moved"
    assert entries[0].category == "Documents"
    assert entries[1].outcome == "corrected"
    assert entries[1].category == "Other"


def test_apply_does_not_record_a_correction_when_the_category_is_unchanged(
    tmp_path: Path, fake_llm_server
) -> None:
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

    the_plan = build_plan(config)
    apply_plan(the_plan, config)

    entries = read_routing_entries(config)
    assert len(entries) == 1
    assert entries[0].outcome == "moved"


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


def test_apply_is_a_noop_when_the_item_is_already_at_its_target(tmp_path: Path) -> None:
    """A --source rescan of a folder already inside dest (e.g. dest's own
    Archives) can compute a target that's the item's own current path.
    Without a same-path check, movefs.unique_target() would see that path
    "already exists" (it's the item itself) and rename it to a pointless
    "-2" sibling of itself.
    """
    config = _config(tmp_path)
    archives = config.dest / "Archives"
    archives.mkdir(parents=True)
    (archives / "mystery.zip").write_bytes(b"unidentified content")

    # Rescan dest's own Archives folder, same as cli.py's --source override.
    rescan_config = config.model_copy(update={"source": archives})
    the_plan = build_plan(rescan_config)

    assert len(the_plan.moves) == 1
    result = apply_plan(the_plan, rescan_config)

    assert result.moved == [(archives / "mystery.zip", archives / "mystery.zip")]
    assert result.held == []
    assert (archives / "mystery.zip").exists()
    assert list(archives.iterdir()) == [archives / "mystery.zip"]  # no -2 sibling
    assert read_entries(config) == []  # nothing to undo, nothing journaled
