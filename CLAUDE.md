# CLAUDE.md

Instructions for working on sort-sys-alpha. Full design: [`PLAN.md`](PLAN.md).
Decision history: [`docs/adr/`](docs/adr/).

## What this is

A CLI that scans a Windows Downloads folder, identifies what each file (and
file group, and subfolder) is (deterministic rules first, a local LLM for the
rest), and files it into a fixed set of folders with a descriptive name.
Developed on Linux, deployed on Windows 11, running against Ollama or
Lemonade on an RTX 5070 Ti.

## Hard rules (do not relax these without the user explicitly signing off)

1. **Rules before the model.** File types the rules tier can settle by
   extension, magic bytes, or header/disc signature (installers, ISOs,
   torrents, ROMs whose console is identifiable) are classified by
   `route.py`'s rules tier and never reach the LLM. Only add an LLM call
   where a rule genuinely can't decide, or for naming a cryptically-named
   file.
2. **Local only.** `config.py` refuses any active backend's `base_url`
   (`model.ollama.base_url` or `model.lemonade.base_url`, whichever
   `model.backend` selects) that isn't a loopback address unless
   `model.allow_remote = true`. Never weaken this check, and never add code
   that sends file contents anywhere but the local model server.
3. **Plan, then apply.** `plan` only ever writes `plan.json` / `report.md`.
   `apply` is the only command that touches files in `source`. Don't merge
   these into one step.
4. **Confidence gate is in code, not in the prompt.** `gate.py` enforces
   `confidence_min`, the folder allowlist (including the resolved
   `ROMs/<console>` entries — see `Config.resolved_folder_allowlist`), name
   safety, the stat/hash-unchanged check, subfolder depth/size limits, and
   "hold the whole group if any member fails" — independently of whatever the
   model claims. A prompt change must never be the only thing standing
   between a low-confidence verdict and a move.
5. **Never delete.** The model may set `suggest_delete: true`; nothing in
   this codebase acts on that automatically. The only removal that ever
   happens is the source side of a verified cross-volume move.
6. **Every move is journaled before it executes**, so `undo` is always
   possible. If you add a new way for `apply.py` to touch the filesystem, it
   must go through `journal.py` first.
7. **`schedule.mode` picks `auto` vs. `plan`, but the gate never bends either
   way** (ADR 0003). `run` is allowed to call `apply` automatically in `auto`
   mode precisely because `gate.py` is what's keeping that safe — don't add
   a shortcut that skips the gate for either mode.

## Repo conventions

- `src/sort_sys_alpha/identify/` is a plugin-per-file-type directory: each
  module exposes `can_handle(evidence) -> bool` and `extract(path) -> dict`.
  Adding a file type means adding one module plus a fixture under
  `tests/fixtures/`, not touching the dispatch logic.
- Use `pathlib` everywhere; no hardcoded `/` or `\` path joins.
- Windows-only behavior (Zone.Identifier ADS, file-lock detection, Task
  Scheduler) lives behind small adapters with Linux no-op/fake
  implementations, so the rest of the suite runs on Linux.
- Config and LLM response schemas are `pydantic` models, not hand-rolled dict
  validation.
- No feature flags or backwards-compat shims for code that hasn't shipped —
  this is pre-release; change the schema/CLI directly instead of versioning
  around it.

## Commands

```sh
uv sync --all-groups          # install deps (incl. dev group)
uv run sort-sys-alpha --help
uv run pytest
uv run ruff check .
```

CI (`.github/workflows/ci.yml`) runs all three on `ubuntu-latest` and
`windows-latest`. If you change CLI behavior, update `tests/test_cli.py`
accordingly — `--help` and the smoke test must keep passing on both.

## Testing

- Unit/integration tests never call a real model: `tests/fake_llm_server.py`
  (M3+) mocks both Ollama's native `/api/chat` and the OpenAI-compatible
  `/chat/completions` Lemonade uses. If you're testing LLM-tier code, point
  it at the fake server for the backend under test, not a live instance.
- Real-model testing happens manually against the Windows PC, either locally
  or over the LAN with `model.allow_remote = true` — this is a dev-only
  override, never the default in checked-in config, and only ever against
  synthetic fixtures, never real personal files.
- Every new extractor in `identify/` needs a fixture in `tests/fixtures/`
  and a test asserting the evidence it produces.
- Every new `gate.py` hold reason needs a fake-server test that triggers it.

## Milestone discipline

PLAN.md section 10 lists milestones M0–M8. Don't jump ahead — e.g. don't wire
up ROM DAT matching (M7) while M1's extractors are still stubs. If a task
implies work from a later milestone, flag it rather than silently expanding
scope.
