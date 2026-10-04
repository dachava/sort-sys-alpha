# ADR 0002: Destination layout and scheduled-run behavior

## Status
Accepted.

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
- The `run` command (M3) composes `plan` + the gate, but does not call
  `apply` automatically; the scheduled task registered in M4 calls `run`
  (plan-only) rather than an auto-apply path.
- Both decisions can be revisited once there's real usage data — nothing here
  prevents adding an opt-in auto-apply mode later behind its own config flag.
