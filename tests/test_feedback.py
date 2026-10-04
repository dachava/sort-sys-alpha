from datetime import UTC, datetime
from pathlib import Path

from sort_sys_alpha.config import Config
from sort_sys_alpha.feedback import (
    original_categories,
    read_routing_entries,
    recent_accepted_examples,
    record_correction,
    record_verdict,
)
from sort_sys_alpha.identify.types import Evidence


def _config(tmp_path: Path) -> Config:
    return Config.model_validate({"dest": str(tmp_path / "_Filed")})


def _evidence(name: str = "mystery.xyz") -> Evidence:
    return Evidence(
        path=Path(name),
        original_name=name,
        extension=Path(name).suffix,
        size=10,
        created=datetime.now(UTC),
        modified=datetime.now(UTC),
        kind="unknown",
    )


def _record(config: Config, move_root: Path, *, outcome: str, category: str = "Documents") -> None:
    record_verdict(
        run_id="run1",
        move_root=move_root,
        evidence=_evidence(move_root.name),
        category=category,
        name="a-mystery-file",
        confidence=0.9,
        reason="looks like a document",
        suggest_delete=False,
        outcome=outcome,
        prompt_version="v1",
        config=config,
    )


def test_record_verdict_round_trips(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _record(config, tmp_path / "a.xyz", outcome="moved")

    entries = read_routing_entries(config)
    assert len(entries) == 1
    assert entries[0].category == "Documents"
    assert entries[0].outcome == "moved"
    assert entries[0].backend == "ollama"


def test_held_verdicts_are_not_treated_as_accepted(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _record(config, tmp_path / "a.xyz", outcome="held")

    assert recent_accepted_examples(config) == []


def test_recent_accepted_examples_excludes_undone(tmp_path: Path) -> None:
    config = _config(tmp_path)
    move_root = tmp_path / "a.xyz"
    _record(config, move_root, outcome="moved")

    assert len(recent_accepted_examples(config)) == 1

    record_correction("run1", move_root, "undone", config)
    assert recent_accepted_examples(config) == []


def test_recent_accepted_examples_includes_corrected(tmp_path: Path) -> None:
    config = _config(tmp_path)
    move_root = tmp_path / "a.xyz"
    _record(config, move_root, outcome="moved", category="Other")

    record_correction("run1", move_root, "corrected", config, category="Documents")

    examples = recent_accepted_examples(config)
    assert len(examples) == 1
    assert examples[0].category == "Documents"
    assert examples[0].outcome == "corrected"


def test_recent_accepted_examples_respects_limit(tmp_path: Path) -> None:
    config = _config(tmp_path)
    for i in range(10):
        _record(config, tmp_path / f"file{i}.xyz", outcome="moved")

    assert len(recent_accepted_examples(config, limit=3)) == 3


def test_record_correction_is_a_noop_without_an_original(tmp_path: Path) -> None:
    config = _config(tmp_path)
    record_correction("run1", tmp_path / "nope.xyz", "undone", config)
    assert read_routing_entries(config) == []


def test_original_categories_only_includes_moved_entries_for_the_run(tmp_path: Path) -> None:
    config = _config(tmp_path)
    moved_root = tmp_path / "moved.xyz"
    held_root = tmp_path / "held.xyz"
    _record(config, moved_root, outcome="moved", category="Documents")
    _record(config, held_root, outcome="held", category="Other")

    categories = original_categories("run1", config)
    assert categories == {moved_root: "Documents"}
