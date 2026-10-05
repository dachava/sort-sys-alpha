"""Accuracy/latency harness for the LLM tier. See PLAN.md section 6 and the
M5 "done when": compare models, context sizes and prompt versions with
numbers rather than vibes.

Each labeled fixture runs through the same `route.resolve()` pipeline a real
run uses, rather than calling a backend directly -- fixtures are deliberately
named (see evals/manifest.toml) so the rules tier can't place them, so in
practice this only ever exercises the LLM tier, but reusing `resolve()` keeps
`eval` honest about what a real run would do. `result.tier` reports which
tier actually answered, as a sanity check that a fixture hasn't started
getting caught by a rule added since it was written.

Comparing models/backends/prompt versions means rerunning `eval` with a
different `--config`, the same way every other command is config-driven --
there's no multi-run orchestration here.
"""

from __future__ import annotations

import statistics
import time
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .identify import identify_item
from .items import FileItem
from .route import resolve

MANIFEST_FILENAME = "manifest.toml"


@dataclass(frozen=True)
class EvalCase:
    file: Path
    expected_category: str


@dataclass(frozen=True)
class EvalResult:
    case: EvalCase
    predicted_category: str | None  # None if the item was held, not routed
    tier: str | None  # "rule" | "llm", or None if held
    latency_s: float
    hold_reason: str | None = None

    @property
    def correct(self) -> bool:
        return self.predicted_category == self.case.expected_category


def load_manifest(evals_dir: Path) -> list[EvalCase]:
    manifest_path = evals_dir / MANIFEST_FILENAME
    if not manifest_path.exists():
        raise FileNotFoundError(f"no eval manifest at {manifest_path}")
    with manifest_path.open("rb") as f:
        data = tomllib.load(f)
    return [
        EvalCase(file=evals_dir / case["file"], expected_category=case["expected_category"])
        for case in data.get("case", [])
    ]


def run_eval(
    evals_dir: Path,
    config: Config,
    *,
    on_case: Callable[[int, int, str], None] | None = None,
) -> list[EvalResult]:
    """`on_case(index, total, label)` fires right before each fixture is
    classified -- same reason as `plan.build_plan`'s `on_item`: this is a
    synchronous LLM call per case, and silence until the whole set finishes
    is indistinguishable from a hang.
    """
    cases = load_manifest(evals_dir)
    total = len(cases)
    results = []
    for index, case in enumerate(cases, start=1):
        if on_case is not None:
            on_case(index, total, case.file.name)
        evidence = identify_item(FileItem(case.file))
        start = time.monotonic()
        verdict, reason = resolve(FileItem(case.file), evidence, config)
        latency = time.monotonic() - start
        if verdict is None:
            results.append(EvalResult(case, None, None, latency, hold_reason=reason))
        else:
            results.append(EvalResult(case, verdict.category, verdict.source, latency))
    return results


def render_report(results: list[EvalResult], config: Config) -> str:
    if not results:
        return "no eval cases found."

    lines = [f"backend: {config.model.backend} ({config.model.active_base_url})"]

    by_category: dict[str, list[EvalResult]] = {}
    for result in results:
        by_category.setdefault(result.case.expected_category, []).append(result)
    for category in sorted(by_category):
        group = by_category[category]
        correct = sum(1 for r in group if r.correct)
        lines.append(f"{category}: {correct}/{len(group)}")

    total = len(results)
    correct = sum(1 for r in results if r.correct)
    lines.append(f"overall: {correct}/{total} ({correct / total:.0%})")

    llm_latencies = [r.latency_s for r in results if r.tier == "llm"]
    if llm_latencies:
        lines.append(
            f"llm latency: mean {statistics.mean(llm_latencies):.2f}s, "
            f"median {statistics.median(llm_latencies):.2f}s ({len(llm_latencies)} case(s))"
        )

    rule_hits = sum(1 for r in results if r.tier == "rule")
    if rule_hits:
        lines.append(
            f"note: {rule_hits} case(s) were caught by the rules tier, not the model -- "
            "consider renaming those fixtures if the goal is comparing models"
        )

    held = [r for r in results if r.predicted_category is None]
    if held:
        lines.append(f"held: {len(held)} case(s) got no verdict")
        for result in held:
            lines.append(f"  {result.case.file.name}: {result.hold_reason}")

    return "\n".join(lines)
