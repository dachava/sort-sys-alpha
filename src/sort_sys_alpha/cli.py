"""CLI entry point. See PLAN.md section 5 for the command contract."""

from __future__ import annotations

import typer

app = typer.Typer(
    name="sort-sys-alpha",
    help="Keep Downloads usable without handing files to a cloud service.",
    no_args_is_help=True,
)


def _not_implemented(command: str, milestone: str) -> None:
    typer.echo(f"'{command}' is not implemented yet (lands in {milestone}).")
    raise typer.Exit(code=1)


@app.command()
def scan() -> None:
    """Inventory + evidence only, no model."""
    _not_implemented("scan", "M1")


@app.command()
def plan() -> None:
    """Produce plan.json + report.md."""
    _not_implemented("plan", "M2")


@app.command()
def apply(
    plan_file: str = typer.Option(None, "--plan", help="Path to a plan.json to execute."),
) -> None:
    """Execute a plan."""
    _not_implemented("apply", "M2")


@app.command()
def run() -> None:
    """Plan + gate, then notify; apply stays a manual step (what the scheduled task calls)."""
    _not_implemented("run", "M3")


@app.command()
def undo(
    run_id: str = typer.Argument("last", help="Run id to undo, or 'last'."),
) -> None:
    """Undo a previous run via the move journal."""
    _not_implemented("undo", "M2")


@app.command(name="eval")
def eval_() -> None:
    """Run the labeled fixture set, print accuracy per category."""
    _not_implemented("eval", "M5")


@app.command()
def doctor() -> None:
    """Check model server, config, and permissions."""
    _not_implemented("doctor", "M3")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
