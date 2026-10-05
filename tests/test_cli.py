from pathlib import Path

from typer.testing import CliRunner

from sort_sys_alpha.cli import _format_duration, _resolved, app

runner = CliRunner()


def test_resolved_only_prints_above_the_slow_threshold(capsys) -> None:
    _resolved(1, 10, "fast.txt", 0.001)
    assert capsys.readouterr().err == ""

    _resolved(2, 10, "slow.xyz", 3.456)
    err = capsys.readouterr().err
    assert "[2/10] slow.xyz" in err
    assert "3.5s" in err


def test_format_duration() -> None:
    assert _format_duration(7) == "7s"
    assert _format_duration(125) == "2m 5s"
    assert _format_duration(3725) == "1h 2m 5s"


def _write_config(tmp_path: Path, source: Path, **extra_lines: str) -> Path:
    # TOML basic strings treat "\" as an escape char, so a raw Windows path
    # (C:\Users\...) isn't valid inside double quotes; posix-style forward
    # slashes parse fine into a Path on every OS.
    config_path = tmp_path / "config.toml"
    lines = [
        f'source = "{source.as_posix()}"',
        f'dest = "{(source / "_Filed").as_posix()}"',
        "min_age_minutes = 0",
    ]
    lines.extend(f"{key} = {value}" for key, value in extra_lines.items())
    config_path.write_text("\n".join(lines) + "\n")
    return config_path


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "sort-sys-alpha" in result.output


def test_subcommands_registered() -> None:
    result = runner.invoke(app, ["--help"])
    for command in ["scan", "plan", "apply", "run", "undo", "eval", "doctor"]:
        assert command in result.output


def test_eval_reports_accuracy(tmp_path: Path, fake_llm_server) -> None:
    evals_dir = tmp_path / "evals"
    evals_dir.mkdir()
    (evals_dir / "mystery.xyz123").write_bytes(b"\x01\x02\x03")
    (evals_dir / "manifest.toml").write_text(
        '[[case]]\nfile = "mystery.xyz123"\nexpected_category = "Documents"\n'
    )
    fake_llm_server.set_ollama_reply(
        '{"kind": "manual", "category": "Documents", "name": "a-mystery-file", '
        '"confidence": 0.9, "reason": "looks like a document"}'
    )
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                "[model.ollama]",
                f'base_url = "{fake_llm_server.base_url}"',
                "",
            ]
        )
    )

    result = runner.invoke(
        app, ["eval", "--config", str(config_path), "--evals-dir", str(evals_dir)]
    )
    assert result.exit_code == 0
    assert "overall: 1/1" in result.output


def test_scan_on_empty_source(tmp_path: Path) -> None:
    source = tmp_path / "Downloads"
    source.mkdir()
    config_path = _write_config(tmp_path, source)

    result = runner.invoke(app, ["scan", "--config", str(config_path)])
    assert result.exit_code == 0
    assert result.output == ""


def test_scan_reports_a_file(tmp_path: Path) -> None:
    source = tmp_path / "Downloads"
    source.mkdir()
    (source / "notes.txt").write_text("hello\n")
    config_path = _write_config(tmp_path, source)

    result = runner.invoke(app, ["scan", "--config", str(config_path)])
    assert result.exit_code == 0
    assert "notes.txt" in result.output


def test_plan_writes_plan_and_report(tmp_path: Path) -> None:
    source = tmp_path / "Downloads"
    source.mkdir()
    (source / "notes.txt").write_text("hello\n")
    config_path = _write_config(tmp_path, source)

    result = runner.invoke(app, ["plan", "--config", str(config_path)])
    assert result.exit_code == 0
    assert "1 to move" in result.output
    assert (source / "_Filed" / ".sort-sys-alpha" / "plan.json").exists()
    assert (source / "_Filed" / ".sort-sys-alpha" / "report.md").exists()
    assert (source / "notes.txt").exists()  # plan never touches source
    assert "done in" in result.output


def test_run_in_plan_mode_never_touches_source(tmp_path: Path) -> None:
    source = tmp_path / "Downloads"
    source.mkdir()
    (source / "notes.txt").write_text("hello\n")
    config_path = _write_config(tmp_path, source, schedule='{ mode = "plan", notify = false }')

    result = runner.invoke(app, ["run", "--config", str(config_path)])
    assert result.exit_code == 0
    assert "1 ready to review" in result.output
    assert (source / "notes.txt").exists()
    assert (source / "_Filed" / ".sort-sys-alpha" / "plan.json").exists()
    assert "done in" in result.output


def test_run_in_auto_mode_moves_files(tmp_path: Path) -> None:
    source = tmp_path / "Downloads"
    source.mkdir()
    (source / "notes.txt").write_text("hello\n")
    config_path = _write_config(tmp_path, source, schedule='{ mode = "auto", notify = false }')

    result = runner.invoke(app, ["run", "--config", str(config_path)])
    assert result.exit_code == 0
    assert "moved 1, held 0" in result.output
    assert not (source / "notes.txt").exists()
    assert "done in" in result.output


def test_apply_without_a_plan_fails_cleanly(tmp_path: Path) -> None:
    source = tmp_path / "Downloads"
    source.mkdir()
    config_path = _write_config(tmp_path, source)

    result = runner.invoke(app, ["apply", "--config", str(config_path)])
    assert result.exit_code == 1
    assert "run `sort-sys-alpha plan` first" in result.output or "plan" in result.output


def test_plan_then_apply_then_undo(tmp_path: Path) -> None:
    source = tmp_path / "Downloads"
    source.mkdir()
    (source / "notes.txt").write_text("hello\n")
    config_path = _write_config(tmp_path, source)

    plan_result = runner.invoke(app, ["plan", "--config", str(config_path)])
    assert plan_result.exit_code == 0

    apply_result = runner.invoke(app, ["apply", "--config", str(config_path)])
    assert apply_result.exit_code == 0
    assert "moved 1, held 0" in apply_result.output
    assert not (source / "notes.txt").exists()

    undo_result = runner.invoke(app, ["undo", "last", "--config", str(config_path)])
    assert undo_result.exit_code == 0
    assert "restored" in undo_result.output
    assert (source / "notes.txt").exists()


def test_doctor_reports_backend_reachability(tmp_path: Path, fake_llm_server) -> None:
    source = tmp_path / "Downloads"
    source.mkdir()
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                f'source = "{source.as_posix()}"',
                f'dest = "{(source / "_Filed").as_posix()}"',
                "[model.ollama]",
                f'base_url = "{fake_llm_server.base_url}"',
                "",
            ]
        )
    )
    fake_llm_server.set_raw_reply({"models": []})

    result = runner.invoke(app, ["doctor", "--config", str(config_path)])
    assert result.exit_code == 0
    assert "source: OK" in result.output
    assert "reachable" in result.output


def test_undo_with_no_runs_fails_cleanly(tmp_path: Path) -> None:
    source = tmp_path / "Downloads"
    source.mkdir()
    config_path = _write_config(tmp_path, source)

    result = runner.invoke(app, ["undo", "last", "--config", str(config_path)])
    assert result.exit_code == 1
    assert "no runs" in result.output
