"""Plan generation: plan.json + report.md. See PLAN.md sections 4.10 and 5.

`plan` only ever writes these two files — it never touches anything in
`source`. `apply` is the only command that moves files.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from .config import Config
from .gate import HoldDecision, MoveDecision, gate_item
from .identify import identify_item
from .items import FileItem, FolderUnit, ScanItem
from .route import RouteVerdict, route
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


def _verdict_for(item: ScanItem, evidence, config: Config) -> RouteVerdict | None:
    if isinstance(item, FolderUnit):
        return RouteVerdict(item.category, 1.0, item.reason)
    return route(evidence, config)


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


def build_plan(config: Config, *, run_id: str | None = None) -> Plan:
    created = datetime.now(UTC)
    run_id = run_id or created.strftime("%Y%m%dT%H%M%S%fZ")

    scan_result = scan(config)
    moves: list[PlanMove] = []
    holds: list[PlanHold] = []

    for item in scan_result.items:
        evidence = identify_item(item)
        verdict = _verdict_for(item, evidence, config)
        decision = gate_item(item, evidence, verdict, config)

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
        lines.append(f"- {sources} -> `{move.target}` ({move.category}, {move.reason})")

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


def write_plan(plan: Plan, config: Config) -> tuple[Path, Path]:
    state_dir = _state_dir(config)
    plan_path = state_dir / PLAN_FILENAME
    report_path = state_dir / REPORT_FILENAME
    plan_path.write_text(plan.model_dump_json(indent=2))
    report_path.write_text(render_report(plan))
    append_held_log(
        [(h.sources[0], h.reason) for h in plan.holds], plan.run_id, "plan", config
    )
    return plan_path, report_path


def load_plan(path: Path) -> Plan:
    return Plan.model_validate_json(path.read_text())
