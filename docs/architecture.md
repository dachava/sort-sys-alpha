# Architecture

Canonical design lives in [`PLAN.md`](../PLAN.md) (section 4, pipeline; section 4.5,
gate rules; section 7, config schema). This doc tracks how that design maps onto
the actual modules, and is updated as milestones land.

```
scan.py ─► subfolders.py ─► duplicates.py ─► identify/ ─► route.py ─► (rules | llm/) ─► gate.py ─► plan.py ─► apply.py ─► journal.py
                                                   ▲                                      │           │           │
                                                   └──────────────── feedback.py ◄────────┴───────────┴───────────┘
```
`feedback.py` is cross-cutting, not another pipeline stage: `plan.py` writes a
`routing.jsonl` entry per LLM verdict, `llm/` reads recent accepted ones back
as few-shot examples, and `apply.py`/`journal.py` append corrections when a
plan edit or an `undo` overrides one.

| Module | Responsibility | Milestone |
|---|---|---|
| `config.py` | Load and validate `config.toml`; enforce the local-only model guard for whichever backend (Ollama/Lemonade) is active | M0 |
| `cli.py` | `scan`, `plan`, `apply`, `run`, `undo`, `eval`, `doctor` | M0 (stubs) → M1/M2 (scan/plan/apply/undo) → M3 (doctor) → M4 (`run`) → M5 (`eval`) |
| `scan.py` | Walk the top level of the source folder, skip partials/locked/recent/hidden files | M1 |
| `groups.py` / `items.py` | File groups and folder units that move as one unit (cue/bin, gdi, m3u, ccd; extracted apps, albums, disc dumps, single-type folders) | M1 / M2 |
| `identify/` | One evidence-extractor plugin per file type, plus ROM headers and ISO9660 disc detection | M1 |
| `subfolders.py` | Classify each subfolder as unit / grab-bag / unsure from markers (PLAN.md 4.2b) | M2 |
| `route.py` | Rules tier (user config rules + built-in kind→category mapping), then `resolve()` calls the LLM tier for whatever rules can't place | M2 / M3 |
| `naming.py` | Fill the default `{date}_{slug}` template from metadata or the original filename | M2 (default template only; per-category templates are M8) |
| `llm/` | Ollama + OpenAI-compatible (Lemonade) clients, versioned prompts, response schema | M3 |
| `gate.py` | Hard safety checks enforced in code, independent of the model's output | M2 (confidence/allowlist/naming/escape checks) → M3 (model-unreachable/invalid-JSON hold reason) |
| `movefs.py` | Shared move/copy+verify/collision primitives used by `apply` and `undo` | M2 |
| `plan.py` | Build `plan.json` + `report.md`, append to `held.log` | M2 |
| `apply.py` | Execute a plan: move/copy, collision handling, staleness re-check, empty-folder reporting | M2 |
| `journal.py` | `journal.jsonl` and `undo` | M2 |
| `notify.py` | Best-effort toast notification after `run`; no-op off Windows | M4 |
| `scripts/windows/` | `install.ps1` (uv + default config), `register-task.ps1` (idle-gated weekly Scheduled Task), `notify.ps1` (the actual toast, shelled out to from `notify.py`) | M4 |
| `feedback.py` | `routing.jsonl`: every LLM-tier verdict, plan edits and undos as corrections, recent-accepted examples for few-shot | M5 |
| `evaluate.py` | `eval` harness: runs `evals/manifest.toml` fixtures through `route.resolve()`, reports accuracy per category and LLM latency | M5 |
| `duplicates.py` | Exact-content duplicate detection for loose files, size-prefiltered before hashing; a confirmed duplicate is held with no identify/route/LLM cost (ADR 0005) | post-M5 |

Decisions with rationale (destination layout, scheduled-run behavior, etc.) are
recorded as ADRs in [`adr/`](adr/).
