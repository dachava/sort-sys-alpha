"""Plan generation: plan.json + report.md. See PLAN.md sections 4.10 and 5.

`plan` only ever writes these two files — it never touches anything in
`source`. `apply` is the only command that moves files.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from . import feedback
from .config import Config
from .duplicates import partition_duplicates
from .gate import HoldDecision, MoveDecision, gate_item
from .identify import identify_item
from .items import FileItem, FolderUnit, ScanItem
from .llm.prompts import PROMPT_VERSION
from .route import resolve, route
from .scan import STATE_DIR_NAME, scan

PLAN_FILENAME = "plan.json"
REPORT_FILENAME = "report.md"
HELD_LOG_FILENAME = "held.log"


class PlanMove(BaseModel):
    sources: list[Path]  # informational: every path swept up by this move
    move_root: Path  # the actual filesystem operation apply() performs: move_root -> target
    category: str
    name: str
    target: Path
    confidence: float
    reason: str
    size: int
    mtime: float
    suggest_delete: bool = False


class PlanHold(BaseModel):
    sources: list[Path]
    reason: str


class Plan(BaseModel):
    run_id: str
    created: datetime
    source: Path
    dest: Path
    moves: list[PlanMove] = Field(default_factory=list)
    holds: list[PlanHold] = Field(default_factory=list)
    # Folders split as grab-bags; apply() checks these for emptiness afterward
    # and reports (never deletes) any that ended up empty. See PLAN.md 4.2b.
    grab_bag_dirs: list[Path] = Field(default_factory=list)


def _item_sources(item: ScanItem) -> list[Path]:
    if isinstance(item, FileItem):
        return [item.path]
    return list(item.members)  # FileGroup | FolderUnit


def _move_root(item: ScanItem) -> Path:
    if isinstance(item, FileItem):
        return item.path
    if isinstance(item, FolderUnit):
        return item.root
    raise NotImplementedError(
        "FileGroup moves aren't implemented — route() never returns a verdict for "
        "disc_group evidence in M2, so this should be unreachable"
    )


def _size_and_mtime(item: ScanItem) -> tuple[int, float]:
    """Staleness baseline for apply-time re-checking (PLAN.md section 4.6).

    A single file's mtime is meaningful and cheap; a folder unit's isn't (it
    reflects the directory entry, not its contents), so only total size is
    tracked for those — apply() re-sums member sizes rather than re-mtime'ing.
    """
    sources = _item_sources(item)
    total_size = sum(p.stat().st_size for p in sources if p.exists())
    if isinstance(item, FileItem) and item.path.exists():
        return total_size, item.path.stat().st_mtime
    return total_size, 0.0


def build_plan(
    config: Config,
    *,
    run_id: str | None = None,
    on_item: Callable[[int, int, str], None] | None = None,
    on_resolved: Callable[[int, int, str, float], None] | None = None,
) -> Plan:
    """`on_item(index, total, label)` fires right before each item is routed
    -- `resolve()` can mean a synchronous LLM call per file, which can take
    anywhere from seconds to over a minute with a large model on first load,
    so a caller without this would see no output at all until every file in
    `source` has been processed. `on_resolved(index, total, label, elapsed_s)`
    fires right after, with how long `identify_item()` + `resolve()`
    together actually took for that item -- the full per-item wall-clock
    cost (evidence extraction can itself be slow for a large/complex file,
    not just the LLM call), not a vibe, for comparing models/backends.

    Exact-content duplicates among loose files (ADR 0005) are partitioned
    out before any of that: they're held immediately, with no identify/
    route/LLM cost at all, so `total`/`on_item`/`on_resolved` only ever see
    the one copy of a duplicate group that proceeds through the pipeline.
    """
    created = datetime.now(UTC)
    run_id = run_id or created.strftime("%Y%m%dT%H%M%S%fZ")

    scan_result = scan(config)
    scan_items, duplicate_holds = partition_duplicates(scan_result.items)
    total = len(scan_items)
    moves: list[PlanMove] = []
    holds: list[PlanHold] = [
        PlanHold(sources=[path], reason=reason) for path, reason in duplicate_holds
    ]

    for index, item in enumerate(scan_items, start=1):
        label = _item_sources(item)[0].name
        if on_item is not None:
            on_item(index, total, label)

        start = time.monotonic()
        evidence = identify_item(item)
        verdict, unresolved_reason = resolve(item, evidence, config)
        elapsed = time.monotonic() - start
        if on_resolved is not None:
            on_resolved(index, total, label, elapsed)

        decision = gate_item(item, evidence, verdict, config, unresolved_reason=unresolved_reason)

        if verdict is not None and verdict.source == "llm":
            feedback.record_verdict(
                run_id=run_id,
                move_root=_move_root(item),
                evidence=evidence,
                category=verdict.category,
                name=verdict.name_hint or "",
                confidence=verdict.confidence,
                reason=verdict.reason,
                latency_s=elapsed,
                suggest_delete=verdict.suggest_delete,
                outcome="moved" if isinstance(decision, MoveDecision) else "held",
                prompt_version=PROMPT_VERSION,
                config=config,
            )

        sources = _item_sources(item)
        if isinstance(decision, MoveDecision):
            size, mtime = _size_and_mtime(item)
            moves.append(
                PlanMove(
                    sources=sources,
                    move_root=_move_root(item),
                    category=decision.category,
                    name=decision.name,
                    target=decision.target,
                    confidence=decision.confidence,
                    reason=decision.reason,
                    size=size,
                    mtime=mtime,
                    suggest_delete=decision.suggest_delete,
                )
            )
        elif isinstance(decision, HoldDecision):
            holds.append(PlanHold(sources=sources, reason=decision.reason))

    for skipped in scan_result.skipped:
        holds.append(PlanHold(sources=[skipped.path], reason=skipped.reason))

    return Plan(
        run_id=run_id,
        created=created,
        source=config.source,
        dest=config.dest,
        moves=moves,
        holds=holds,
        grab_bag_dirs=scan_result.grab_bag_dirs,
    )


def build_rename_plan(
    config: Config,
    *,
    path: Path | None = None,
    run_id: str | None = None,
    on_item: Callable[[int, int, str], None] | None = None,
) -> Plan:
    """Recompute names for files already filed under `dest` -- scoped to
    `path` if given, else the whole filed tree -- using today's naming
    templates. See `docs/adr/0012-rename-only-run.md`.

    Reuses `gate_item()` for every existing safety check (confidence, name
    safety, the ADR 0009 duplicate-against-dest check, ...) by re-running
    identify/route fresh on each file and gating the result exactly like a
    normal plan would. One rule on top of that gate.py doesn't itself
    know about: a verdict whose category disagrees with the file's
    *current* folder is held, never used to move it to a different
    category -- re-triaging category is `--source`'s job; this only ever
    renames a file within the folder it's already in. Rules tier only, no
    LLM call, so this stays fast and free to run on a whole filed tree.

    Only loose files are considered -- a `FolderUnit`'s own name (a whole
    directory) is out of scope here, same as ADR 0009's duplicate check.
    """
    created = datetime.now(UTC)
    run_id = run_id or created.strftime("%Y%m%dT%H%M%S%fZ")
    root = path or config.dest
    state_dir = config.dest / STATE_DIR_NAME

    try:
        files = sorted(
            p for p in root.rglob("*") if p.is_file() and state_dir not in (p, *p.parents)
        )
    except OSError:
        files = []

    total = len(files)
    moves: list[PlanMove] = []
    holds: list[PlanHold] = []

    for index, file in enumerate(files, start=1):
        if on_item is not None:
            on_item(index, total, file.name)

        try:
            current_category = file.parent.relative_to(config.dest).as_posix()
        except ValueError:
            continue  # not actually under dest -- ignore, not ours to rename

        evidence = identify_item(FileItem(file))
        verdict = route(evidence, config)
        if verdict is None:
            holds.append(PlanHold(sources=[file], reason="no rule-tier verdict to rename from"))
            continue

        decision = gate_item(FileItem(file), evidence, verdict, config)
        if isinstance(decision, HoldDecision):
            holds.append(PlanHold(sources=[file], reason=decision.reason))
            continue

        if decision.category != current_category:
            holds.append(
                PlanHold(
                    sources=[file],
                    reason=(
                        f"fresh identification suggests {decision.category!r}, not its "
                        f"current {current_category!r} -- re-triage with --source instead "
                        "of renaming in place"
                    ),
                )
            )
            continue

        if decision.target == file:
            continue  # name already matches today's template, nothing to do

        moves.append(
            PlanMove(
                sources=[file],
                move_root=file,
                category=decision.category,
                name=decision.name,
                target=decision.target,
                confidence=decision.confidence,
                reason=decision.reason,
                size=file.stat().st_size,
                mtime=file.stat().st_mtime,
                suggest_delete=decision.suggest_delete,
            )
        )

    return Plan(
        run_id=run_id, created=created, source=root, dest=config.dest, moves=moves, holds=holds
    )


def _state_dir(config: Config) -> Path:
    state_dir = config.dest / STATE_DIR_NAME
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def render_report(plan: Plan) -> str:
    lines = [
        f"# sort-sys-alpha plan — {plan.run_id}",
        "",
        f"Source: `{plan.source}`  ",
        f"Dest: `{plan.dest}`",
        "",
        f"## Moves ({len(plan.moves)})",
        "",
    ]
    for move in plan.moves:
        sources = ", ".join(f"`{s}`" for s in move.sources)
        note = " **[model suggests deleting after review]**" if move.suggest_delete else ""
        lines.append(f"- {sources} -> `{move.target}` ({move.category}, {move.reason}){note}")

    lines += ["", f"## Held ({len(plan.holds)})", ""]
    for hold in plan.holds:
        sources = ", ".join(f"`{s}`" for s in hold.sources)
        lines.append(f"- {sources}: {hold.reason}")

    return "\n".join(lines) + "\n"


def append_held_log(
    entries: list[tuple[Path, str]], run_id: str, phase: str, config: Config
) -> None:
    """held.log is append-only (PLAN.md section 4.10): every run adds to it,
    unlike plan.json/report.md, which reflect only the latest run.
    """
    if not entries:
        return
    path = _state_dir(config) / HELD_LOG_FILENAME
    timestamp = datetime.now(UTC).isoformat()
    with path.open("a", encoding="utf-8") as f:
        for item_path, reason in entries:
            f.write(f"{timestamp} run={run_id} phase={phase} {item_path}: {reason}\n")


def write_plan(plan: Plan, config: Config, label: str | None = None) -> tuple[Path, Path]:
    """`label` (typically the --source override's own folder name, see
    cli.py) names the output files `plan-<label>.json`/`report-<label>.md`
    instead of the default `plan.json`/`report.md`, so re-triaging a
    different folder doesn't overwrite the normal run's report.
    """
    state_dir = _state_dir(config)
    plan_name = f"plan-{label}.json" if label else PLAN_FILENAME
    report_name = f"report-{label}.md" if label else REPORT_FILENAME
    plan_path = state_dir / plan_name
    report_path = state_dir / report_name
    plan_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    report_path.write_text(render_report(plan), encoding="utf-8")
    append_held_log(
        [(h.sources[0], h.reason) for h in plan.holds], plan.run_id, "plan", config
    )
    return plan_path, report_path


def load_plan(path: Path) -> Plan:
    return Plan.model_validate_json(path.read_text(encoding="utf-8"))
