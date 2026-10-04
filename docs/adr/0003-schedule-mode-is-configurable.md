# ADR 0003: Scheduled run mode is configurable (`auto` / `plan`)

## Status
Accepted. Supersedes decision 2 of [ADR 0002](0002-destination-and-scheduled-run-defaults.md).

## Context
ADR 0002 fixed the scheduled run to plan-only: produce `plan.json` /
`report.md`, notify, and require a manual `apply`. The project scope grew to
cover subfolders, file groups, and ROM/disc routing (PLAN.md section 4), all
still gated by the same ≥0.75 confidence check and folder allowlist as plain
files. With those gates doing the real safety work regardless of file type,
forcing every scheduled run through a manual `apply` step stopped being the
only reasonable default — some users will want the weekly run to just file
what clears the gate, same as the article that inspired this project.

## Decision
The scheduled run's behavior is a config choice, not a fixed one:

- `schedule.mode = "auto"` — `run` does `plan` + `apply` through the same
  gates as a manual run. This is the default.
- `schedule.mode = "plan"` — `run` does `plan` only; `apply` stays manual.
- `schedule.notify = true` sends a toast either way: a summary of moved/held/
  suggested-deletion counts in `auto`, or "N files ready to review" in `plan`.

## Consequences
- `config.py`'s `ScheduleConfig` holds `mode` and `notify`; `Config` has no
  single fixed scheduled behavior.
- `run` (M3) must branch on `schedule.mode` rather than always stopping after
  `plan` — PLAN.md section 5 describes it as "plan + apply with gates (what
  the scheduler calls)" again, with the gate being what makes `auto` safe,
  not the absence of an apply step.
- `CLAUDE.md`'s hard rule about the scheduled run being plan-only is replaced
  by a rule that the gate, not the schedule mode, is what must stay safe:
  `auto` must never bypass `gate.py`.
- The Scheduled Task script (M4) doesn't need two variants; it always calls
  `run`, and `schedule.mode` decides what that does.