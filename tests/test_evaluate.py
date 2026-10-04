from pathlib import Path

import pytest

from sort_sys_alpha.config import Config
from sort_sys_alpha.evaluate import load_manifest, render_report, run_eval


def _manifest(evals_dir: Path, *cases: tuple[str, str]) -> None:
    evals_dir.mkdir(exist_ok=True)
    lines = []
    for file, expected_category in cases:
        lines.append("[[case]]")
        lines.append(f'file = "{file}"')
        lines.append(f'expected_category = "{expected_category}"')
    (evals_dir / "manifest.toml").write_text("\n".join(lines) + "\n")


def _config(base_url: str) -> Config:
    return Config.model_validate({"model": {"backend": "ollama", "ollama": {"base_url": base_url}}})


def test_load_manifest_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_manifest(tmp_path)


def test_load_manifest_parses_cases(tmp_path: Path) -> None:
    (tmp_path / "a.xyz").write_bytes(b"\x00")
    _manifest(tmp_path, ("a.xyz", "Documents"))

    cases = load_manifest(tmp_path)
    assert len(cases) == 1
    assert cases[0].file == tmp_path / "a.xyz"
    assert cases[0].expected_category == "Documents"


def test_run_eval_marks_llm_hits(tmp_path: Path, fake_llm_server) -> None:
    (tmp_path / "mystery.xyz123").write_bytes(b"\x01\x02\x03")
    _manifest(tmp_path, ("mystery.xyz123", "Documents"))
    fake_llm_server.set_ollama_reply(
        '{"kind": "manual", "category": "Documents", "name": "a-mystery-file", '
        '"confidence": 0.9, "reason": "looks like a document"}'
    )

    results = run_eval(tmp_path, _config(fake_llm_server.base_url))
    assert len(results) == 1
    assert results[0].tier == "llm"
    assert results[0].correct is True


def test_run_eval_reports_a_hold(tmp_path: Path) -> None:
    (tmp_path / "mystery.xyz123").write_bytes(b"\x01\x02\x03")
    _manifest(tmp_path, ("mystery.xyz123", "Documents"))

    config = _config("http://127.0.0.1:1")  # nothing listens here
    results = run_eval(tmp_path, config)

    assert results[0].predicted_category is None
    assert results[0].correct is False
    assert "unreachable" in results[0].hold_reason


def test_render_report_summarizes_accuracy_and_holds(tmp_path: Path) -> None:
    (tmp_path / "mystery.xyz123").write_bytes(b"\x01\x02\x03")
    _manifest(tmp_path, ("mystery.xyz123", "Documents"))

    config = _config("http://127.0.0.1:1")
    results = run_eval(tmp_path, config)
    report = render_report(results, config)

    assert "Documents: 0/1" in report
    assert "overall: 0/1 (0%)" in report
    assert "held: 1 case(s)" in report


def test_render_report_with_no_results() -> None:
    assert render_report([], Config()) == "no eval cases found."
