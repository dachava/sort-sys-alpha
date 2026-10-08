# SORT-SYS-ALPHA: a local-LLM file sorter for Windows (plan)

> Project: **SORT-SYS-ALPHA**. Repo and CLI: `sort-sys-alpha`, Python package: `sort_sys_alpha`
> Status: planning. Built with Claude Code from a Linux dev box, and the target is Windows 11.
> Model runtime: Ollama (native Windows app, already installed) and Lemonade, both supported from day one. Hardware: RTX 5070 Ti, 16 GB.
> Inspired by XDA's "I put a local model in charge of naming and filing every download".

## 1. Goal

Keep `Downloads` usable without handing files to a cloud service. The tool figures out **what every file is**,
gives it a descriptive name, and files it into a fixed set of folders. It **never deletes** anything and
**never moves a file it isn't sure about**.

This is the **first module** of SORT-SYS-ALPHA (the Downloads module). Other modules come later (see §12), but v1
stays focused on Downloads.

Non-goals for v1: other folders, sync, a GUI. (De-duplication was originally
out of scope too, but exact-content duplicate detection for loose files was
added after real usage showed the same readme/license/installer repeated
dozens of times across unrelated downloads -- see ADR 0005. The same check
was extended to cover a loose file matching something already filed from an
earlier run, not just within one scan batch -- see ADR 0009. Folder-level
and archive-content dedup remain out of scope.)

## 2. Principles (from the article, kept as hard rules)

1. **Boring rules first, LLM second.** Folders are mostly by file type, so most routing is deterministic (extension, magic bytes, ROM/disc headers). The model handles naming cryptic files and the cases the rules can't settle.
2. **Local only.** The model server (Ollama or Lemonade) runs on the same PC over localhost. File contents never leave the machine, and the config refuses non-loopback endpoints unless an explicit override flag is set.
3. **Plan, then apply.** Pass one produces a plan with confidence scores and proposed names. Pass two executes it. The scheduled run's mode is set in config: `auto` (plan + apply through the same gates) or `plan` (plan only). Both modes send a notification.
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
- Subfolders inside Downloads are sorted too (see §4.2b).

### 4.2 File groups
Some files only work together, so the core moves **groups**, not just single files:
- `.cue` + its `.bin` track files (parsed from the cue sheet)
- `.gdi` + its track files (Dreamcast)
- `.m3u` + the discs it lists (multi-disc games)
- `.ccd` + `.img` + `.sub`

A group is planned, gated and moved as one unit: if any member fails a check, the whole group is held. Later modules reuse this
(an album folder: FLAC files + `.cue` + cover art).

### 4.2b Subfolders (hybrid)
Every subfolder of Downloads (except `_Filed`) is classified first as either a **unit** or a **grab-bag**:

| Verdict | Signals | What happens |
|---|---|---|
| **Unit**: moves intact, internal structure untouched | extracted app (`.exe` + `.dll`s, `setup.exe`), game dump / disc set, album (audio + `.cue` + cover), code project (`.git`, `package.json`, `pyproject.toml`, `*.tf`), a folder of only one type (all images → `Images\<folder name>`) | the whole folder moves to one category, e.g. `ROMs\ps2\<name>\`, `Installers\<name>\`, `Images\<name>\` |
| **Grab-bag**: split | mixed, unrelated files with no project or app markers | each file (and file group) is sorted individually like a top-level file; nested folders get the same unit/grab-bag check |
| **Unsure** | low confidence, conflicting signals | the folder is held as a whole, nothing inside moves |

- Deterministic markers decide first. The model gets a **listing** (names, sizes, types, first N entries, marker files found) and only
  decides when markers don't settle it. The same 0.75 confidence gate applies.
- Units go into the existing allowlisted categories: there's no separate "Folders" category.
- **Empty folders left behind are never deleted by `plan`/`apply`/`run`.** They stay and are listed in
  `report.md` under suggested deletions. Removing them is a separate, explicit step: the `prune` command
  (ADR 0006), run manually, never as part of plan/apply/run.
- Limits: max depth and max file count per folder (config), so a huge folder is held instead of producing a 5,000-line plan.

### 4.3 Identify: "what could this be?"
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
| Archives | member list (first 20 entries), total size; never extract | "a zipped GBA ROM", "contains .tf files", "a mod pack" |
| Logs | timestamp-per-line / log-level patterns in the first lines | `.log`, but also `.txt` files that are really logs |
| Executables | PE version info (`pefile`): ProductName, CompanyName, FileVersion; MSI properties | "7-Zip 24.08 x64 installer" |
| Disk images | ISO volume label (`pycdlib`), plus console disc signatures (see §4.9) | "Ubuntu 24.04 live" vs a PS2 disc |
| ROMs | extension + header signatures (iNES, N64 byte order, Sega header, GameCube/Wii disc magic, `SYSTEM.CNF` on PS1/PS2) | which console it belongs to |
| Audio/video | tags and duration (`mutagen`, `ffprobe` if present) | — |
| Fonts | family / style name table (`fontTools`) | — |
| Torrents | bencode `name` | — |
| Unknown | first 512 bytes as a hex/printable preview | gives the model *something* to go on |

Each extractor is a small plugin: `can_handle(evidence) -> bool`, `extract(path) -> dict`. Adding a file type
means adding one module plus a fixture.

### 4.4 Route
- **Tier 1, rules:** configurable rules matched on *true type*, extension, header signature and/or source host. Because the
  folders are mostly by type, this tier routes most files: images, audio, PDFs, notes, logs, ISOs, installers, and ROMs whose
  console is identified by extension or header. Rule hits still get a better name from the metadata (for example PE ProductName +
  version) with no model call.
- **Tier 2, LLM:** files the rules can't settle (an unknown extension, an ambiguous `.bin`/`.iso`/`.zip`, a `.txt` that might be a
  log) and naming for files with cryptic names (`IMG_4031.png`, `document(3).pdf`). The model gets the evidence bundle, plus the
  image or rendered page if it supports vision.

### 4.5 LLM contract
- Servers: **both from day one**, chosen in config, both on the Windows PC (RTX 5070 Ti, 16 GB VRAM):
  - **Ollama** (native Windows app, already installed) at `http://localhost:11434`. Open WebUI stays as the chat front-end and isn't in this tool's path.
  - **Lemonade** (installed alongside it) at `http://localhost:13305/api/v1`, its OpenAI-compatible API.
  - Both use llama.cpp-family engines on CUDA, so speed should be similar. `eval --backend ollama|lemonade` measures it on this
    hardware: accuracy, latency per file, VRAM use. Only one server should hold a model in VRAM at a time.
- Client: a small `Backend` interface with two implementations:
  - `OllamaBackend` (default) uses the **native** `/api/chat` API, because it exposes things the OpenAI-compatible endpoint doesn't:
    - `format`: a full JSON schema, so the reply is constrained to the response schema below
    - `options.num_ctx`: Ollama's default context is small. An evidence bundle plus an image needs roughly 8k, so set it explicitly
    - `keep_alive`: a short value (for example `2m`) unloads the model after a run and frees VRAM for games
    - `think: false`: for reasoning models, so they don't produce long thinking output
    - `images`: base64 images for vision models
  - `OpenAICompatBackend` handles Lemonade, and works with LM Studio or llama.cpp `llama-server` for free. It uses `response_format` with a JSON schema
    where supported, otherwise `json_object`.
- `doctor` checks the setup for each backend. For Ollama: `/api/tags` (is the model pulled?) and `/api/show` (does `capabilities` include `vision`?).
  For Lemonade: `/api/v1/models`. If the model has no vision, image and scanned-PDF evidence is sent as metadata only.
- Model names differ between servers (`qwen2.5vl:7b` in Ollama vs a GGUF checkpoint name in Lemonade), so config holds a name per backend.
- Request: system prompt (rules, folder allowlist, naming style, a few recent accepted examples) + evidence JSON.
- Validation: pydantic on every reply, even with schema-constrained output. Strip any `<think>` blocks before parsing.
- Candidate models: 16 GB fits 7–14B vision models at Q4/Q8 with room for context. Shortlist for `eval` (check current tags
  on ollama.com): `qwen2.5vl:7b`, `qwen3-vl:8b`, `gemma3:12b`, plus a text-only model for comparison. Choose by eval numbers,
  not by guessing.
- Response schema:
  ```json
  {
    "kind": "router manual",
    "category": "Documents",
    "name": "gl-inet-flint-2-user-guide",
    "confidence": 0.86,
    "reason": "PDF from gl-inet.com, title 'GL-MT6000 User Guide'",
    "suggest_delete": false
  }
  ```

### 4.6 Gate (all hard rules, enforced in code, not in the prompt)
A file is **held** (stays where it is and gets logged with a reason) when any of these apply:
- `confidence < 0.75`
- `category` is not in the allowlist (the model tried to invent a folder)
- the name is empty or unsafe after slugifying, or the path would escape the destination root
- the model is unreachable, times out, or returns invalid JSON
- the file changed between plan and apply (size/mtime/hash mismatch)
- a subfolder is classified as unsure, or exceeds the depth/size limits
- the item is a type the config marks as `always_hold`
- any member of a file group fails a check (the whole group is held)
- a naming template needs a field nobody could fill

### 4.7 Apply
- Target: `<dest>\<Category>\<name from the category's naming template><ext>` (see §4.8). The default template is
  `{title}` -- a human-readable name, not a date-prefixed slug (ADR 0010).
- Never overwrite: collisions get a `-2`, `-3` suffix.
- Move = same-volume rename. Cross-volume = copy, verify the hash, then remove the source (the only "delete" in the system, and it's part of a move).
- Every move is written to `journal.jsonl` *before* it executes.

### 4.8 Naming conventions (ADR 0010)
Every filed file gets a name that follows a **per-category template**, filled from metadata. The model's job is to
extract *fields*, not to write free-form names. Templates live in config, and default to `{title}` for every category:

```toml
[naming]
default = "{title}"      # human-readable, sanitized for Windows, not lowercased/hyphenated
```

`{title}` is the counterpart to the older `{slug}` (still available, just no longer the default): it takes the same
source -- a DAT title, a PE `ProductName`, an LLM-proposed name, or the original filename -- and only strips
Windows-illegal characters, leaving case/spacing/punctuation alone. `{date}` is also still available for anyone who
wants a date-prefixed template back for a specific category. Fields come from deterministic metadata first (EXIF
date, PE version, DAT match) and from the model second. A field the template needs but nobody could fill → the file
is held (it's not renamed with a gap).

### 4.9 ROMs and disc images
- Folders use **EmuDeck/RetroArch names** (`snes`, `nes`, `n64`, `gb`, `gbc`, `gba`, `nds`, `fds`, `gc`, `wii`, `psx`, `ps2`, `psp`,
  `genesis`, `saturn`, `dreamcast`, `pcenginecd`, `msx`, `gamegear`, `mastersystem`, `sega32x`, `sg1000`, …), so `ROMs\` can be
  copied straight to the Steam Deck. The exact list should be checked against EmuDeck's docs when implemented.
- Detection order: extension → header/disc signature → zip member inspection → model (the model is the last resort, with low default trust).
- `.iso` / `.bin` / `.chd`: a console disc signature sends the file to `ROMs\<console>`. No signature: a PC/Linux/software disc goes to `ISOs\`.
- `.zip` / `.7z`: if the members are ROMs of a single console, the archive goes to `ROMs\<console>` (it stays zipped). Otherwise it goes to `Archives\`.
- Arcade sets (MAME/FBNeo zips) can't be identified from headers, so they're held until DAT matching exists.
- **DAT matching (M7, started):** two shapes, both local libretro DATs via `roms.dat_files`:
  - PS1/PS2/PSP discs get an exact title by looking up the serial read from `SYSTEM.CNF` against a
    serial-keyed "Data Center" DAT (ADR 0007) -- no content hash involved.
  - Cartridge consoles (NES/SNES/Genesis/GBA/N64/GB/GBC/GameGear/32X/SG-1000/MasterSystem, …) get an exact
    title by CRC32 of the whole ROM file against a "libretro-database" developer DAT (ADR 0008).
  - Arcade sets, and byte-for-byte dump *verification* against No-Intro/Redump (as opposed to title lookup),
    are separate, not-yet-built scope.

### 4.10 Outputs (in `<dest>\.sort-sys-alpha\`)
| File | Purpose |
|---|---|
| `plan.json` | the latest plan, can be edited by hand before `apply` (override a category or name) |
| `report.md` | human-readable plan: moves, holds with reasons, suggested deletions (including empty folders left behind) |
| `routing.jsonl` | every verdict ever made: evidence summary, model, prompt version, confidence, outcome |
| `held.log` | an append-only list of files left behind and why |
| `journal.jsonl` | moves, used for `undo` |

## 5. CLI

```
sort-sys-alpha scan [--source DIR] # inventory + evidence only, no model (great for debugging extractors)
sort-sys-alpha plan [--source DIR] # produce plan.json + report.md
sort-sys-alpha apply [--plan FILE] # execute a plan
sort-sys-alpha run [--source DIR]  # plan + apply with gates (what the scheduler calls)
sort-sys-alpha undo [RUN_ID|last]
sort-sys-alpha eval                # run the labeled fixture set, print accuracy per category
sort-sys-alpha doctor              # check model server, config, permissions
sort-sys-alpha prune               # remove empty folders under source, recursively (ADR 0006)
```

`--source` overrides `config.toml`'s `source` for one run without editing the file -- e.g. re-triaging
`dest\Archives` after a detection improvement: `plan --source dest\Archives` (dest stays as configured,
so re-identified items land in their real category instead of back in Archives). The override's own
folder name labels the output (`report-Archives.md`/`plan-Archives.json`) instead of the usual
`report.md`/`plan.json`, so a rescan never clobbers a normal run's report.

## 6. Feedback loop ("it learns")
No fine-tuning. Learning comes from data:
1. **Few-shot from history:** recent accepted, non-undone LLM verdicts are injected as examples.
2. **Corrections:** edits to `plan.json` before apply, and `undo`s, are logged as negative or corrected examples.
3. **Eval set:** a `evals/` folder of anonymized fixtures with expected categories. Use it to compare models, context sizes and
   prompt versions with numbers rather than vibes. This also gives the blog post real data.

## 7. Configuration (`config.toml`)
```toml
source = "~/Downloads"
dest = "~/Downloads/_Filed"   # decided: inside Downloads; the scanner always skips _Filed
min_age_minutes = 30
confidence_min = 0.75

[schedule]
mode = "auto"                      # "auto" = plan + apply through the gates; "plan" = plan only, apply manually
notify = true                      # toast in both modes: auto = moved/held/suggested deletions; plan = "N files ready to review"

[model]
backend = "ollama"                 # "ollama" | "lemonade"
vision = "auto"                    # detected per backend
timeout_s = 120
allow_remote = false

[model.ollama]
base_url = "http://localhost:11434"
name = "qwen2.5vl:7b"              # placeholder until eval picks a winner
num_ctx = 8192
keep_alive = "2m"                  # free VRAM soon after a run

[model.lemonade]
base_url = "http://localhost:13305/api/v1"
name = ""                          # GGUF checkpoint name as Lemonade lists it

[folders]
# The allowlist. The model can only pick from these; anything else = held.
allow = ["Images", "Audio", "Documents", "Documents/Notes", "Documents/Logs",
         "ROMs/<console>",            # <console> must be in roms.consoles
         "ISOs", "Archives", "Installers", "Other"]

[roms]
consoles = ["nes", "snes", "n64", "gb", "gbc", "gba", "nds", "gc", "wii",
            "psx", "ps2", "psp", "genesis", "saturn", "dreamcast"]   # extend as needed

[roms.dat_files]
# console = local DAT path; a console with no entry here keeps today's
# behavior (ISO volume label / bare filename as the name). PS1/PS2/PSP use
# a serial-keyed "Data Center" DAT (ADR 0007); cartridge consoles use a
# CRC32-keyed "libretro-database" developer DAT (ADR 0008) -- same config
# shape, the matching key used is picked by the file's kind, not by config.
ps2 = "~/dat/ps2.dat"
snes = "~/dat/snes.dat"

[[rules]]
match = { ext = [".txt", ".md"] }
folder = "Documents/Notes"            # unless log detection says it's a log

[[rules]]
match = { ext = [".log"] }
folder = "Documents/Logs"

[[rules]]
match = { true_type = ["application/x-msdownload", "application/x-msi"] }
folder = "Installers"

[naming]
# default is "{title}" (ADR 0010) -- override any category explicitly:
Installers = "{slug}"     # hyphenated single string, e.g. "7-zip-24-08-x64"

[subfolders]
mode = "hybrid"          # unit / grab-bag / unsure
max_depth = 4
max_files = 500          # above this the folder is held
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
│   └── fake_llm_server.py  # deterministic mock of both Ollama /api/chat and OpenAI /chat/completions
├── evals/
└── .github/workflows/ci.yml  # ubuntu + windows matrix
```

## 9. Developing on Linux for Windows
- Use `pathlib` everywhere. Windows-only features (ADS, file locks, Task Scheduler) sit behind small adapters with Linux no-op/fake implementations.
- Unit and integration tests run against the **fake LLM server**, so CI never needs a model.
- Real-model testing from Linux: point at the Windows PC over the LAN with `allow_remote = true`. For Ollama, set `OLLAMA_HOST=0.0.0.0`
  in the Windows user environment and restart the app. For Lemonade, bind it to the LAN address. Turn both off again after dev sessions.
  Use synthetic fixtures only, never real personal files.
- Windows coverage comes from the `windows-latest` CI job, plus manual runs on the PC with `plan` before `apply`.

## 10. Milestones

| # | Milestone | Done when |
|---|---|---|
| M0 | Repo skeleton, CLAUDE.md, CI matrix, config loading | `uv run sort-sys-alpha --help` passes on both OSes |
| M1 | Scan + identify (`scan` command), file groups, ROM/disc header detection | evidence JSON is correct for every fixture type; bin/cue sets detected as one group |
| M2 | Rules tier + plan/apply/undo + journal, subfolder unit/grab-bag detection from markers | installers/ISOs filed and undone safely; marker-based folders moved intact; empty folders reported, not deleted |
| M3 | LLM tier (Ollama + Lemonade backends) + gate + reports | fake-server tests cover every hold reason on both backends |
| M4 | Windows: Zone.Identifier, lock detection, Scheduled Task script (runs only when the PC is idle, so it doesn't compete with games for the GPU), `auto`/`plan` modes, toast notifications | weekly run on the real PC in both modes |
| M5 | Feedback + `eval` | accuracy and latency for 2–3 models × Ollama vs Lemonade |
| M6 | Vision (images, scanned PDFs), blog post | — |
| M7 | ROM DAT matching (No-Intro/Redump, local DAT files) | exact titles for hashed ROMs -- PS1/PS2/PSP serial matching done (ADR 0007) and cartridge CRC32 matching done (ADR 0008); arcade sets and byte-for-byte dump verification still open |
| M8 | Naming conventions: per-category templates, field extraction, rename-only runs | `{title}` default done (ADR 0010); per-category overrides, full field extraction, and rename-only runs still open |

## 11. Decisions

**Decided (2026-10-04)**
- **Runtime:** Ollama and Lemonade, both supported from day one, selected in config and benchmarked in M5.
- **Ollama install:** native Windows app.
- **Destination:** inside Downloads at `Downloads\_Filed\<Category>\`.
- **Scheduled behaviour:** both modes in config (`auto` / `plan`), and both notify.
- **Hardware:** RTX 5070 Ti, 16 GB. Vision is practical.
- **Folders:** few and mostly by type: Images, Audio, Documents (+ Notes, Logs), ROMs\<console>, ISOs, Archives, Installers, Other.
- **ROM folder names:** EmuDeck/RetroArch style.
- **ROM hashing:** headers + extensions first, DAT matching in a later milestone (M7).
- **Naming:** standardized names via templates are the goal (M8).
- **Music module:** a note only for now (§12).

- **Subfolders:** sorted too, hybrid: coherent units move intact, grab-bags are split, unsure is held.
- **Empty folders:** left in place by plan/apply/run and listed as suggested deletions; removed only by
  the separate, manual `prune` command (ADR 0006) -- hard rule 5's one deliberate, scoped exception.
- **Naming default:** `{title}` (human-readable, sanitized, no date prefix) for every category, not a
  date-prefixed slug (ADR 0010) -- `{slug}`/`{date}` stay available for a custom per-category override.

**Still open**
1. **Per-category naming overrides:** whether any category wants something other than the new `{title}`
   default (needed to finish M8).

## 12. Future modules (notes only)
- **Music → FLAC library:** read a separate music downloads folder and move/sort into the FLAC library folder by tags
  (artist/album/track), keeping album groups together. It reuses the core: scan, identify, groups, gate, plan/apply/undo, journal.
  Not designed yet. The core is refactored into engine + modules when this starts.
