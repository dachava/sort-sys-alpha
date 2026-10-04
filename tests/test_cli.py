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
    # TOML basic strings treat "\" as an escape char, so a raw Windows path
    # (C:\Users\...) isn't valid inside double quotes; posix-style forward
    # slashes parse fine into a Path on every OS.
    config_path.write_text(
        f'source = "{source.as_posix()}"\ndest = "{(source / "_Filed").as_posix()}"\n'
    )

    result = runner.invoke(app, ["scan", "--config", str(config_path)])
    assert result.exit_code == 0
    assert result.output == ""


def test_scan_reports_a_file(tmp_path) -> None:
    source = tmp_path / "Downloads"
    source.mkdir()
    (source / "notes.txt").write_text("hello\n")
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'source = "{source.as_posix()}"\n'
        f'dest = "{(source / "_Filed").as_posix()}"\n'
        "min_age_minutes = 0\n"
    )

    result = runner.invoke(app, ["scan", "--config", str(config_path)])
    assert result.exit_code == 0
    assert "notes.txt" in result.output
