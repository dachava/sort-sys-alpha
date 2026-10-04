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
    result = runner.invoke(app, ["scan"])
    assert result.exit_code == 1
    assert "M1" in result.output
