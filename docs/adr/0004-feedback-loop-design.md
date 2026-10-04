# ADR 0004: Feedback loop design (routing.jsonl, few-shot, corrections)

## Status
Accepted.

## Context
PLAN.md section 6 describes three pieces of "it learns" (no fine-tuning):
recent accepted LLM verdicts shown back as few-shot examples, plan edits and
undos logged as corrections/negative examples, and an `evals/` fixture set
for comparing models with numbers. Section 4.10 says `routing.jsonl` records
"every verdict ever made: evidence summary, model, prompt version,
confidence, outcome." Implementing this (M5) required a few decisions
PLAN.md left open.

## Decisions
1. **`routing.jsonl` only records LLM-tier verdicts.** Rule-tier verdicts are
   deterministic and always confidence 1.0; the feedback loop exists purely
   to make the *model* better, so there's nothing to learn from a rule hit.
   `RouteVerdict.source` (`"rule"` | `"llm"`) is how `plan.build_plan` tells
   them apart.
2. **Append-only, latest-wins.** Like `journal.jsonl`/`held.log`, nothing in
   `routing.jsonl` is ever rewritten in place. A plan edit or an `undo`
   appends a new record for the same `(run_id, move_root)`; readers
   (`recent_accepted_examples`, `original_categories`) resolve history by
   taking the latest record per key.
3. **Few-shot examples are positive-only.** `recent_accepted_examples` shows
   the model only verdicts whose latest outcome is still `"moved"` or
   `"corrected"` — never `"undone"` ones framed as "don't do this." Negative
   examples are still logged (for later analysis, and so eval numbers can
   account for them), just not injected into the live prompt: a small local
   model is more likely to get confused by negative framing than helped by
   it.
4. **Corrections are category-only.** `apply_plan` compares each move's
   current `category` against the category `routing.jsonl` recorded at plan
   time, and logs a `"corrected"` entry only when that changed. A pure
   rename (editing `name` without changing `category`) isn't tracked as a
   correction — that's a naming-template concern (PLAN.md M8), not a routing
   one, and conflating the two would mean comparing a raw model-proposed
   slug against a fully templated, extensioned filename, which isn't a fair
   comparison anyway.
5. **`eval` reuses `route.resolve()`, not a direct backend call.** Fixtures
   in `evals/manifest.toml` are named with extensions the rules tier doesn't
   recognize (`.dat`/`.bin`), so `resolve()` only ever falls through to the
   LLM tier for them — the same code path a real run takes. `EvalResult.tier`
   reports which tier actually answered, so a fixture that starts getting
   caught by a rule (e.g. after a new rule is added) is visible rather than
   silently no longer testing what it was meant to.
6. **No multi-model/backend orchestration in `eval` itself.** Comparing
   "2-3 models × Ollama vs Lemonade" (PLAN.md's M5 done-when) means rerunning
   `sort-sys-alpha eval --config <other config>`, same as every other
   config-driven command. Building a harness that sweeps multiple configs in
   one invocation isn't needed for that and would be new surface area this
   project doesn't need yet.

## Consequences
- `llm/backend.py`'s two `classify()` methods now call
  `recent_accepted_examples(config)` and pass the result into
  `build_system_prompt`, so every LLM call reads `routing.jsonl` history.
- `apply.py` and `journal.py` both import `feedback.py`; `feedback.py`
  imports nothing from either, so there's no cycle.
- `evals/manifest.toml` + `evals/fixtures/` ship a small scaffold set (5
  cases); PLAN.md section 6 expects the user to extend it with real,
  anonymized, ambiguous Downloads files over time.
