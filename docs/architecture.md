# Architecture

Canonical design lives in [`PLAN.md`](../PLAN.md) (section 4, pipeline; section 4.5,
gate rules; section 7, config schema). This doc tracks how that design maps onto
the actual modules, and is updated as milestones land.

```
scan.py ─► identify/ ─► route.py ─► (rules | llm/) ─► gate.py ─► plan.py ─► apply.py ─► journal.py
```

| Module | Responsibility | Milestone |
|---|---|---|
| `config.py` | Load and validate `config.toml`; enforce the local-only model guard for whichever backend (Ollama/Lemonade) is active | M0 |
| `cli.py` | `scan`, `plan`, `apply`, `run`, `undo`, `eval`, `doctor` | M0 (stubs) |
| `scan.py` | Walk the source folder, skip partials/locked/recent files | M1 |
| `identify/` | One evidence-extractor plugin per file type | M1 |
| `route.py` | Rules tier, then LLM tier for the rest | M2 / M3 |
| `llm/` | OpenAI-compatible client, versioned prompts, response schema | M3 |
| `gate.py` | Hard safety checks enforced in code, independent of the model's output | M3 |
| `plan.py` | Build `plan.json` + `report.md` | M2 |
| `apply.py` | Execute a plan: move/copy, collision handling, verification | M2 |
| `journal.py` | `journal.jsonl` and `undo` | M2 |

Decisions with rationale (destination layout, scheduled-run behavior, etc.) are
recorded as ADRs in [`adr/`](adr/).
