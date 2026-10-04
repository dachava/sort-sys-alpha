"""CLI entry point. See PLAN.md section 5 for the command contract."""

from __future__ import annotations

from pathlib import Path

import typer

from .apply import apply_plan
from .config import load_config
from .identify import identify_item
from .journal import last_run_id, undo_run
from .llm.backend import describe_backend
from .notify import notify
from .plan import PLAN_FILENAME, build_plan, load_plan, write_plan
from .scan import STATE_DIR_NAME
from .scan import scan as run_scan

app = typer.Typer(
    name="sort-sys-alpha",
    help="Keep Downloads usable without handing files to a cloud service.",
    no_args_is_help=True,
)


def _not_implemented(command: str, milestone: str) -> None:
    typer.echo(f"'{command}' is not implemented yet (lands in {milestone}).")
    raise typer.Exit(code=1)


@app.command()
def scan(
    config_path: Path | None = typer.Option(None, "--config", help="Path to config.toml."),
) -> None:
    """Inventory + evidence only, no model (great for debugging extractors)."""
    config = load_config(config_path)
    result = run_scan(config)

    for item in result.items:
        evidence = identify_item(item)
        typer.echo(evidence.model_dump_json())

    for skipped in result.skipped:
        typer.echo(f"# skipped: {skipped.path} ({skipped.reason})", err=True)


@app.command()
def plan(
    config_path: Path | None = typer.Option(None, "--config", help="Path to config.toml."),
) -> None:
    """Produce plan.json + report.md."""
    config = load_config(config_path)
    the_plan = build_plan(config)
    plan_path, report_path = write_plan(the_plan, config)
    typer.echo(f"{len(the_plan.moves)} to move, {len(the_plan.holds)} held.")
    typer.echo(f"plan: {plan_path}")
    typer.echo(f"report: {report_path}")


@app.command()
def apply(
    config_path: Path | None = typer.Option(None, "--config", help="Path to config.toml."),
    plan_file: Path | None = typer.Option(None, "--plan", help="Path to a plan.json to execute."),
) -> None:
    """Execute a plan."""
    config = load_config(config_path)
    path = plan_file or (config.dest / STATE_DIR_NAME / PLAN_FILENAME)
    if not path.exists():
        typer.echo(f"no plan found at {path}; run `sort-sys-alpha plan` first.", err=True)
        raise typer.Exit(code=1)

    the_plan = load_plan(path)
    result = apply_plan(the_plan, config)
    typer.echo(f"moved {len(result.moved)}, held {len(result.held)}.")
    for folder in result.emptied_folders:
        typer.echo(f"# left empty, not deleted: {folder}", err=True)


@app.command()
def run(
    config_path: Path | None = typer.Option(None, "--config", help="Path to config.toml."),
) -> None:
    """Plan + apply with gates. `schedule.mode` picks auto vs. plan-only for the scheduled task."""
    config = load_config(config_path)
    the_plan = build_plan(config)
    plan_path, report_path = write_plan(the_plan, config)

    if config.schedule.mode == "plan":
        typer.echo(f"{len(the_plan.moves)} ready to review.")
        typer.echo(f"plan: {plan_path}")
        typer.echo(f"report: {report_path}")
        if config.schedule.notify:
            notify("sort-sys-alpha", f"{len(the_plan.moves)} files ready to review")
        return

    result = apply_plan(the_plan, config)
    typer.echo(f"moved {len(result.moved)}, held {len(result.held)}.")
    for folder in result.emptied_folders:
        typer.echo(f"# left empty, not deleted: {folder}", err=True)

    if config.schedule.notify:
        moved_roots = {root for root, _ in result.moved}
        suggested = sum(
            1 for move in the_plan.moves if move.suggest_delete and move.move_root in moved_roots
        )
        summary = f"moved {len(result.moved)}, held {len(result.held)}"
        if suggested:
            summary += f", {suggested} suggested for deletion"
        notify("sort-sys-alpha", summary)


@app.command()
def undo(
    run_id: str = typer.Argument("last", help="Run id to undo, or 'last'."),
    config_path: Path | None = typer.Option(None, "--config", help="Path to config.toml."),
) -> None:
    """Undo a previous run via the move journal."""
    config = load_config(config_path)
    resolved_id = last_run_id(config) if run_id == "last" else run_id
    if resolved_id is None:
        typer.echo("no runs in the journal yet.", err=True)
        raise typer.Exit(code=1)

    for message in undo_run(resolved_id, config):
        typer.echo(message)


@app.command(name="eval")
def eval_() -> None:
    """Run the labeled fixture set, print accuracy per category."""
    _not_implemented("eval", "M5")


@app.command()
def doctor(
    config_path: Path | None = typer.Option(None, "--config", help="Path to config.toml."),
) -> None:
    """Check model server, config, and permissions."""
    config = load_config(config_path)

    typer.echo(f"source: {'OK' if config.source.is_dir() else 'NOT FOUND'} ({config.source})")
    typer.echo(f"dest: {config.dest}")

    for line in describe_backend(config):
        typer.echo(line)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
