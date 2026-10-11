from pathlib import Path

from sort_sys_alpha.config import Config
from sort_sys_alpha.gate import HoldDecision, MoveDecision, gate_item
from sort_sys_alpha.identify import build_evidence, identify_item
from sort_sys_alpha.items import FileGroup, FileItem, FolderUnit
from sort_sys_alpha.route import RouteVerdict, route


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


def test_unresolved_reason_overrides_the_default_message(tmp_path: Path) -> None:
    path = tmp_path / "mystery.bin"
    path.write_bytes(b"\x00")
    evidence = build_evidence(path)

    decision = gate_item(
        FileItem(path),
        evidence,
        None,
        _config(tmp_path),
        unresolved_reason="model unreachable at http://localhost:11434",
    )
    assert isinstance(decision, HoldDecision)
    assert decision.reason == "model unreachable at http://localhost:11434"


def test_suggest_delete_passes_through_to_the_move_decision(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("hi")
    evidence = build_evidence(path)
    verdict = RouteVerdict("Documents/Notes", 0.9, "model verdict", suggest_delete=True)

    decision = gate_item(FileItem(path), evidence, verdict, _config(tmp_path))
    assert isinstance(decision, MoveDecision)
    assert decision.suggest_delete is True


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


def test_wrong_case_category_is_normalized_not_held(tmp_path: Path) -> None:
    # Regression: an LLM verdict can echo back a category in different case
    # than the allowlist shows it ("roms/ps1" vs "ROMs/ps1") -- the model
    # was shown the exact casing, but nothing guarantees it repeats it, and
    # that's a gate.py job to tolerate, not a prompt-wording fix.
    path = tmp_path / "notes.txt"
    path.write_text("hi")
    evidence = build_evidence(path)
    verdict = RouteVerdict("documents/notes", 0.9, "model verdict")

    decision = gate_item(FileItem(path), evidence, verdict, _config(tmp_path))
    assert isinstance(decision, MoveDecision)
    assert decision.category == "Documents/Notes"
    assert decision.target == _config(tmp_path).dest / "Documents/Notes" / decision.name


def test_ps1_console_alias_is_normalized_to_psx(tmp_path: Path) -> None:
    # Regression: a real run showed the model saying "ROMs/ps1" where the
    # config's canonical console name is "psx" -- a different word, not a
    # case variant, for the console people casually call "PS1".
    path = tmp_path / "SCPH1001.BIN"
    path.write_bytes(b"\x00")
    evidence = build_evidence(path)
    verdict = RouteVerdict("ROMs/ps1", 0.9, "model verdict")

    decision = gate_item(FileItem(path), evidence, verdict, _config(tmp_path))
    assert isinstance(decision, MoveDecision)
    assert decision.category == "ROMs/psx"


def test_valid_move_produces_a_target_under_dest(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("hi")
    evidence = build_evidence(path)
    verdict = RouteVerdict("Documents/Notes", 1.0, "note")
    config = _config(tmp_path)

    decision = gate_item(FileItem(path), evidence, verdict, config)
    assert isinstance(decision, MoveDecision)
    assert decision.target == config.dest / "Documents/Notes" / decision.name
    assert decision.name == "notes.txt"


def test_exact_duplicate_of_already_filed_file_is_held(tmp_path: Path) -> None:
    config = _config(tmp_path)
    existing = config.dest / "Documents/Notes" / "2026-01-01_old-copy.txt"
    existing.parent.mkdir(parents=True)
    existing.write_text("same content")

    path = tmp_path / "notes.txt"
    path.write_text("same content")
    evidence = build_evidence(path)
    verdict = RouteVerdict("Documents/Notes", 1.0, "note")

    decision = gate_item(FileItem(path), evidence, verdict, config)
    assert isinstance(decision, HoldDecision)
    assert decision.reason == f"exact duplicate of {existing}, left in place"


def test_same_size_but_different_content_is_not_held_as_duplicate(tmp_path: Path) -> None:
    config = _config(tmp_path)
    existing = config.dest / "Documents/Notes" / "2026-01-01_other.txt"
    existing.parent.mkdir(parents=True)
    existing.write_text("content A")

    path = tmp_path / "notes.txt"
    path.write_text("content B")  # same length, different bytes
    evidence = build_evidence(path)
    verdict = RouteVerdict("Documents/Notes", 1.0, "note")

    decision = gate_item(FileItem(path), evidence, verdict, config)
    assert isinstance(decision, MoveDecision)


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
    assert decision.name == "MyApp"


def test_file_group_target_keeps_the_primarys_original_filename(tmp_path: Path) -> None:
    """A disc group's members keep their own filenames -- renaming would
    mean rewriting the .cue sheet's internal FILE references too, out of
    scope (ADR 0014). Only the folder should change.
    """
    from fixtures.make import make_raw_cd_bin

    cue = tmp_path / "2026-01-01_old-slug.cue"
    bin_ = tmp_path / "2026-01-01_old-slug.bin"
    cue.write_text('FILE "2026-01-01_old-slug.bin" BINARY\n')
    system_cnf = b"BOOT = cdrom:\\SCUS_123.45;1\r\n"
    make_raw_cd_bin(bin_, volume_id="GAME", root_files={"SYSTEM.CNF": system_cnf}, mode=2)
    group = FileGroup("cue_bin", cue, (cue, bin_))

    config = _config(tmp_path)
    evidence = identify_item(group)
    verdict = route(evidence, config)
    assert verdict is not None

    decision = gate_item(group, evidence, verdict, config)
    assert isinstance(decision, MoveDecision)
    assert decision.target.name == cue.name
    assert decision.target.parent == config.dest / "ROMs" / "psx"
