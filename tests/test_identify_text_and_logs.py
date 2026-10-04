from pathlib import Path

from sort_sys_alpha.identify import build_evidence


def test_python_file_gets_language_and_preview(tmp_path: Path) -> None:
    path = tmp_path / "script.py"
    path.write_text("import os\n\nprint('hi')\n")

    evidence = build_evidence(path)
    assert evidence.kind == "text"
    assert evidence.details["language"] == "python"
    assert "print" in evidence.details["text_preview"]


def test_dot_log_file_is_a_log(tmp_path: Path) -> None:
    path = tmp_path / "server.log"
    path.write_text("2026-01-01 12:00:00 INFO started\n2026-01-01 12:00:01 ERROR boom\n")

    evidence = build_evidence(path)
    assert evidence.kind == "log"
    assert "ERROR" in evidence.details["line_preview"]


def test_txt_file_that_is_really_a_log(tmp_path: Path) -> None:
    path = tmp_path / "output.txt"
    lines = [f"2026-01-01 12:00:{i:02d} INFO tick {i}" for i in range(10)]
    path.write_text("\n".join(lines))

    evidence = build_evidence(path)
    assert evidence.kind == "log"


def test_txt_file_that_is_just_notes(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("Buy milk\nCall mom\nFinish the report\n")

    evidence = build_evidence(path)
    assert evidence.kind == "text"
    assert evidence.details["language"] is None
