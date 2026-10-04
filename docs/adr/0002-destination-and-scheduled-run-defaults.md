# ADR 0002: Destination layout and scheduled-run behavior

## Status
Decision 1 (destination) accepted. Decision 2 (scheduled behavior) superseded
by [ADR 0003](0003-schedule-mode-is-configurable.md).

## Context
PLAN.md section 11 left two open decisions that affect the config schema and
the `run` command's default behavior:

1. Where filed files land: a subfolder inside `Downloads` vs. a separate root
   (e.g. `Documents\Filed`).
2. What the weekly scheduled run does: auto-apply everything that clears the
   confidence gate (as in the article that inspired this project), or produce
   a plan and notify, leaving `apply` as a manual step.

## Decision
1. **Destination:** `~/Downloads/_Filed`, a subfolder inside Downloads. Filed
   output stays next to the unsorted files it came from rather than moving to
   a separate root, which keeps browsing simple during early use while the
   gate and prompts are still being tuned.
2. **Scheduled behavior:** plan-only + notification. The Scheduled Task (M4)
   runs `plan`, produces `plan.json` / `report.md`, and fires a toast; `apply`
   stays a manual, deliberate step the user runs after reviewing the report.

## Consequences
- `config.py`'s default `dest` is `~/Downloads/_Filed` (see PLAN.md section 7).
- Decision 2 held only through the initial M0 scaffold. See ADR 0003 for why
  it changed to a config-selectable `auto`/`plan` mode instead of a fixed
  plan-only behavior, and what that means for `run` and the scheduled task.
