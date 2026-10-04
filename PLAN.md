# SORT-SYS-ALPHA: a local-LLM file sorter for Windows (plan)

> Project: **SORT-SYS-ALPHA**. Repo and CLI: `sort-sys-alpha`, Python package: `sort_sys_alpha`
> Status: planning. Built with Claude Code from a Linux dev box, and the target is Windows 11.
> Inspired by XDA's "I put a local model in charge of naming and filing every download".

## 1. Goal

Keep `Downloads` usable without handing files to a cloud service. The tool figures out **what every file is**,
gives it a descriptive name, and files it into a fixed set of folders. It **never deletes** anything and
**never moves a file it isn't sure about**.

Non-goals for v1: cleaning up the rest of the disk, de-duplication, sync, a GUI.

## 2. Principles (from the article, kept as hard rules)

1. **Boring rules first, LLM second.** File types that are easy to replace (installers, ISOs) go to a deterministic tier. The model only handles what rules can't.
2. **Local only.** The model server runs on the same PC over localhost. File contents never leave the machine, and the config refuses non-loopback endpoints unless an explicit override flag is set.
3. **Plan, then apply.** Pass one produces a plan with confidence scores and proposed names. Pass two executes it. A scheduled run may do both, but only through the same safety gates.
4. **Nothing moves unless it's confident.** A file needs ≥ 0.75 confidence to move. Anything below that stays put and is logged with the reason.
5. **The model can't go off-script.** It picks from an allowlist of destination folders and can't create new ones. Its output has to pass schema validation or the file is held.
6. **Never delete.** The model may *suggest* a deletion. Only the user acts on it.
7. **Everything is reversible and logged.** A move journal supports `undo`, and a routing log records every verdict.

## 3. Language and platform decision

| Option | Pros | Cons |
|---|---|---|
| **Python (recommended core)** | Fits your learning goals. Develop and test on Linux, run on Windows. Mature libraries for identifying file types. Easy to test. | Needs Python on Windows (solved with `uv`) |
| PowerShell only | Native on Windows, easy scheduled tasks, built-in ADS access | Weaker libraries for parsing file formats, harder to test on Linux |

**Proposal:** a Python package as the core, plus a **thin PowerShell layer** only for Windows plumbing:
registering the weekly Scheduled Task, an optional toast notification, and an install script. Python can read
`Zone.Identifier` streams on Windows itself (`open(path + ":Zone.Identifier")`), so no PowerShell is needed there.

Tooling: `uv` for env and packaging, `pytest`, `ruff`, `pydantic` for schemas, `typer` for the CLI,
and GitHub Actions with an **ubuntu + windows-latest** test matrix.

## 4. Architecture

```
scan ─► identify ─► route ─► (rules | llm) ─► gate ─► plan.json ─► apply ─► journal
                                                         │
                                               report.md / held.log
```

### 4.1 Scan
- Source: `%USERPROFILE%\Downloads` (configurable).
- Skip: partial downloads (`.crdownload`, `.part`, `.tmp`, `.opdownload`), anything modified in the last N minutes,
  files locked by another process (Windows), hidden/system files, and our own state folder.
- Folders inside Downloads (extracted zips) are treated as a single item in v1 and are **held by default**.

### 4.2 Identify: "what could this be?"
This is the core of the project. Every file gets an **evidence bundle**, built cheaply and deterministically,
before any model is involved.

| Signal | How | Why |
|---|---|---|
| True type | magic bytes (`puremagic`, pure Python, no libmagic needed on Windows) | catches renamed files and missing or incorrect extensions |
| Download source | `Zone.Identifier` → `HostUrl`, `ReferrerUrl` | "came from github.com/…/releases" or "from my bank's site" is a strong signal |
| Basic stats | size, created/modified, original name | — |
| Images | EXIF (camera, software, date), dimensions, "looks like a screenshot" heuristics | screenshot vs photo vs wallpaper |
| PDF | `pdfinfo`/`pypdf` metadata, first ~40 lines of text, page count; render page 1 if it's a scan | invoices, statements, manuals |
| Office (docx/xlsx/pptx) | core properties (title, author), first lines / sheet names / slide titles | — |
| Text/code/config | first ~40 lines, detected language | `.tf`, `.py`, `.json`, `.yaml` |
| Archives | member list (first 20 entries), total size; never extract | "contains .tf files", "a mod pack" |
| Executables | PE version info (`pefile`): ProductName, CompanyName, FileVersion; MSI properties | "7-Zip 24.08 x64 installer" |
| Disk images | ISO volume label (`pycdlib`) | "Ubuntu 24.04 live" |
| Audio/video | tags and duration (`mutagen`, `ffprobe` if present) | — |
| Fonts | family / style name table (`fontTools`) | — |
| Torrents | bencode `name` | — |
| Unknown | first 512 bytes as a hex/printable preview | gives the model *something* to go on |

Each extractor is a small plugin: `can_handle(evidence) -> bool`, `extract(path) -> dict`. Adding a file type
means adding one module plus a fixture.

### 4.3 Route
- **Tier 1, rules:** configurable rules matched on *true type* and/or extension and/or source host.
  Default rules cover replaceable things only: installers, ISOs, torrents. Rule hits still get a better name from
  the metadata (for example the PE ProductName + version) with no model call.
- **Tier 2, LLM:** everything else gets the evidence bundle (plus the image or rendered page if the model supports vision).

### 4.4 LLM contract
- Server: **Lemonade** on Windows (an OpenAI-compatible API on localhost), with `Qwen3.5-9B-GGUF` as the
  starting model. On the Linux dev box it's Lemonade or Ollama with the same API, so only the config changes.
- Request: system prompt (rules, folder allowlist, naming style, a few recent accepted examples) + evidence JSON.
- Structured output: JSON schema via `response_format` where the server supports it. Otherwise `json_object`,
  validated with pydantic. Strip any `<think>` blocks before parsing.
- Response schema:
  ```json
  {
    "kind": "bank statement",
    "category": "Bank & Finance",
    "name": "chase-statement-2026-08",
    "confidence": 0.86,
    "reason": "PDF from chase.com, header 'Statement Period Aug 2026'",
    "suggest_delete": false
  }
  ```

### 4.5 Gate (all hard rules, enforced in code, not in the prompt)
A file is **held** (stays where it is and gets logged with a reason) when any of these apply:
- `confidence < 0.75`
- `category` is not in the allowlist (the model tried to invent a folder)
- the name is empty or unsafe after slugifying, or the path would escape the destination root
- the model is unreachable, times out, or returns invalid JSON
- the file changed between plan and apply (size/mtime/hash mismatch)
- the item is a folder, or a type the config marks as `always_hold`

### 4.6 Apply
- Target: `<dest>\<Category>\<YYYY-MM-DD>_<name><ext>`. The date prefix is the move date.
- Never overwrite: collisions get a `-2`, `-3` suffix.
- Move = same-volume rename. Cross-volume = copy, verify the hash, then remove the source (the only "delete" in the system, and it's part of a move).
- Every move is written to `journal.jsonl` *before* it executes.

### 4.7 Outputs (in `<dest>\.sort-sys-alpha\`)
| File | Purpose |
|---|---|
| `plan.json` | the latest plan, can be edited by hand before `apply` (override a category or name) |
| `report.md` | human-readable plan: moves, holds with reasons, suggested deletions |
| `routing.jsonl` | every verdict ever made: evidence summary, model, prompt version, confidence, outcome |
| `held.log` | an append-only list of files left behind and why |
| `journal.jsonl` | moves, used for `undo` |

## 5. CLI

```
sort-sys-alpha scan                # inventory + evidence only, no model (great for debugging extractors)
sort-sys-alpha plan                # produce plan.json + report.md
sort-sys-alpha apply [--plan FILE] # execute a plan
sort-sys-alpha run                 # plan + gate, notify; apply stays manual (what the scheduled task calls)
sort-sys-alpha undo [RUN_ID|last]
sort-sys-alpha eval                # run the labeled fixture set, print accuracy per category
sort-sys-alpha doctor              # check model server, config, permissions
```

## 6. Feedback loop ("it learns")
No fine-tuning. Learning comes from data:
1. **Few-shot from history:** recent accepted, non-undone LLM verdicts are injected as examples.
2. **Corrections:** edits to `plan.json` before apply, and `undo`s, are logged as negative or corrected examples.
3. **Eval set:** a `evals/` folder of anonymized fixtures with expected categories. Use it to compare models, context sizes and
   prompt versions with numbers rather than vibes. This also gives the blog post real data.

## 7. Configuration (`config.toml`)
```toml
source = "~/Downloads"
dest = "~/Downloads/_Filed"   # subfolder inside Downloads (decided)
min_age_minutes = 30
confidence_min = 0.75

[model]
base_url = "http://localhost:8000/api/v1"  # Lemonade; Ollama = http://localhost:11434/v1
name = "Qwen3.5-9B-GGUF"
vision = true
timeout_s = 120
allow_remote = false

[folders]
allow = ["Installers", "Disk Images", "Screenshots", "Photos", "Receipts & Invoices",
         "Bank & Finance", "Work", "Personal Documents", "Guides & Manuals", "Diagrams",
         "Code & Config", "Archives", "Audio", "Video", "Fonts", "3D Models", "Other"]

[[rules]]
match = { true_type = ["application/x-msdownload", "application/x-msi"] }
folder = "Installers"
```

## 8. Repo layout

```
sort-sys-alpha/
├── CLAUDE.md               # instructions for Claude Code: rules, commands, conventions
├── README.md
├── PLAN.md                 # this file
├── docs/
│   ├── architecture.md
│   └── adr/                # decision records (Python vs PS, gating, etc.) – blog fodder
├── pyproject.toml
├── src/sort_sys_alpha/
│   ├── cli.py  config.py  scan.py  route.py  gate.py  plan.py  apply.py  journal.py
│   ├── identify/           # one module per extractor
│   └── llm/                # client, prompt templates (versioned), schema
├── scripts/windows/
│   ├── install.ps1         # uv + config + scheduled task
│   └── register-task.ps1   # weekly Scheduled Task
├── tests/
│   ├── fixtures/           # tiny sample files of each type
│   └── fake_llm_server.py  # deterministic OpenAI-compatible mock
├── evals/
└── .github/workflows/ci.yml  # ubuntu + windows matrix
```

## 9. Developing on Linux for Windows
- Use `pathlib` everywhere. Windows-only features (ADS, file locks, Task Scheduler) sit behind small adapters with Linux no-op/fake implementations.
- Unit and integration tests run against the **fake LLM server**, so CI never needs a model.
- Real-model testing on Linux: Lemonade/Ollama on deimos, pointed at with `allow_remote = true` (dev only).
- Windows coverage comes from the `windows-latest` CI job, plus manual runs on the PC with `plan` before `apply`.

## 10. Milestones

| # | Milestone | Done when |
|---|---|---|
| M0 | Repo skeleton, CLAUDE.md, CI matrix, config loading | `uv run sort-sys-alpha --help` passes on both OSes |
| M1 | Scan + identify (`scan` command) | evidence JSON is correct for every fixture type |
| M2 | Rules tier + plan/apply/undo + journal | installers/ISOs filed and undone safely, no model needed |
| M3 | LLM tier + gate + reports | fake-server tests cover every hold reason |
| M4 | Windows: Zone.Identifier, lock detection, Scheduled Task script | weekly run on the real PC |
| M5 | Feedback + `eval` | accuracy numbers for 2–3 models |
| M6 | Vision (images, scanned PDFs), toast notification, blog post | — |

## 11. Open decisions

1. **Destination:** ~~subfolders inside Downloads (`_Filed\…`) or a separate root (for example `Documents\Filed`)?~~
   **Decided:** subfolder inside Downloads (`~/Downloads/_Filed`). See `docs/adr/0002-destination-and-scheduled-run-defaults.md`.
2. **Scheduled behaviour:** ~~auto-apply what passes the gate (as in the article), or plan-only + notification, then a manual apply?~~
   **Decided:** plan-only + notification; `apply` stays a manual, deliberate step. See `docs/adr/0002-destination-and-scheduled-run-defaults.md`.
3. **Hardware on the Windows PC:** GPU/VRAM decides 9B vs a smaller model and whether vision is practical.
4. **Folder allowlist:** the starting categories above, or your own taxonomy?
5. **Folders in Downloads:** always hold, or let the model classify them from a listing?
