from datetime import date
from pathlib import Path

from sort_sys_alpha.config import Config
from sort_sys_alpha.gate import HoldDecision, MoveDecision, gate_item
from sort_sys_alpha.identify import build_evidence
from sort_sys_alpha.items import FileItem, FolderUnit
from sort_sys_alpha.route import RouteVerdict


def _config(tmp_path: Path, **overrides) -> Config:
    data = {"dest": str(tmp_path / "_Filed")}
    data.update(overrides)
    return Config.model_validate(data)


def test_no_verdict_is_held(tmp_path: Path) -> None:
    path = tmp_path / "mystery.bin"
    path.write_bytes(b"\x00")
    evidence = build_evidence(path)

    decision = gate_item(FileItem(path), evidence, None, _config(tmp_path))
    assert isinstance(decision, HoldDecision)
    assert "no matching rule" in decision.reason


def test_low_confidence_is_held(tmp_path: Path) -> None:
    path = tmp_path / "photo.txt"
    path.write_text("hi")
    evidence = build_evidence(path)
    verdict = RouteVerdict("Documents/Notes", 0.5, "weak guess")

    decision = gate_item(FileItem(path), evidence, verdict, _config(tmp_path))
    assert isinstance(decision, HoldDecision)
    assert "confidence" in decision.reason


def test_category_not_in_allowlist_is_held(tmp_path: Path) -> None:
    path = tmp_path / "photo.txt"
    path.write_text("hi")
    evidence = build_evidence(path)
    verdict = RouteVerdict("Nonexistent Category", 1.0, "made up")

    decision = gate_item(FileItem(path), evidence, verdict, _config(tmp_path))
    assert isinstance(decision, HoldDecision)
    assert "allowlist" in decision.reason


def test_valid_move_produces_a_target_under_dest(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("hi")
    evidence = build_evidence(path)
    verdict = RouteVerdict("Documents/Notes", 1.0, "note")
    config = _config(tmp_path)

    decision = gate_item(FileItem(path), evidence, verdict, config)
    assert isinstance(decision, MoveDecision)
    assert decision.target == config.dest / "Documents/Notes" / decision.name
    assert decision.name.startswith(date.today().isoformat())
    assert decision.name.endswith(".txt")


def test_folder_unit_target_has_no_extension(tmp_path: Path) -> None:
    root = tmp_path / "MyApp"
    root.mkdir()
    (root / "setup.exe").write_bytes(b"\x00")
    unit = FolderUnit(root, "Installers", "extracted app markers", (root / "setup.exe",))
    evidence = build_evidence(root)
    verdict = RouteVerdict("Installers", 1.0, "extracted app markers")

    decision = gate_item(unit, evidence, verdict, _config(tmp_path))
    assert isinstance(decision, MoveDecision)
    assert decision.target.suffix == ""
    assert "myapp" in decision.name
