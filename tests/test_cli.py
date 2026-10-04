from typer.testing import CliRunner

from sort_sys_alpha.cli import app

runner = CliRunner()


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "sort-sys-alpha" in result.output


def test_subcommands_registered() -> None:
    result = runner.invoke(app, ["--help"])
    for command in ["scan", "plan", "apply", "run", "undo", "eval", "doctor"]:
        assert command in result.output


def test_unimplemented_command_exits_nonzero() -> None:
    result = runner.invoke(app, ["plan"])
    assert result.exit_code == 1
    assert "M2" in result.output


def test_scan_on_empty_source(tmp_path) -> None:
    source = tmp_path / "Downloads"
    source.mkdir()
    config_path = tmp_path / "config.toml"
    config_path.write_text(f'source = "{source}"\ndest = "{source / "_Filed"}"\n')

    result = runner.invoke(app, ["scan", "--config", str(config_path)])
    assert result.exit_code == 0
    assert result.output == ""


def test_scan_reports_a_file(tmp_path) -> None:
    source = tmp_path / "Downloads"
    source.mkdir()
    (source / "notes.txt").write_text("hello\n")
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'source = "{source}"\n'
        f'dest = "{source / "_Filed"}"\n'
        "min_age_minutes = 0\n"
    )

    result = runner.invoke(app, ["scan", "--config", str(config_path)])
    assert result.exit_code == 0
    assert "notes.txt" in result.output
