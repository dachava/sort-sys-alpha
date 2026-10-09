# sort-sys-alpha

A local-LLM file sorter for Windows Downloads folders. Figures out what a file is, gives it a descriptive name, and files it into a fixed set of folders, never deleting or moving anything it isn't confident about.

Deterministic rules (extension, magic bytes, header/disc signatures) settle almost everything; a local LLM (Ollama or Lemonade, nothing ever leaves the machine) only handles the genuinely ambiguous cases and naming cryptic files.

## Status

Implemented: scan, identify (one plugin per file type), rules-tier + LLM-tier routing, the confidence gate, plan/apply/undo, subfolder handling (unit/grab-bag/unsure), duplicate detection (within a scan batch and against already-filed content), the scheduled `run` command (`auto`/`plan` modes + toast notifications), the feedback loop (`routing.jsonl`, few-shot examples, plan-edit/undo corrections, `eval`), the `prune` command, and ROM DAT title matching for both disc serials (PS1/PS2/PSP) and cartridge CRC32 (NES, SNES, Genesis, GBA, N64, GB/GBC, FDS, Game Gear, Master System, 32X, SG-1000, and any other libretro-database console DAT you add) — including inside a single-game zip/7z, not just loose files. Naming defaults to a human-readable `{title}` (no date prefix), and the `rename` command re-applies today's naming templates to already-filed files without recategorizing them. Vision (M6) is explicitly deprioritized — routing is format-based, not content-based, so it wouldn't change any decision this tool makes.
Per-category naming overrides and arcade/hash-keyed No-Intro dump verification remain open.

## Setup (Windows)

```powershell
git clone <this repo's URL>
cd sort-sys-alpha
.\scripts\windows\install.ps1          # installs uv, syncs the env, writes a default config.toml
.\scripts\windows\register-task.ps1    # registers the weekly Scheduled Task (idle-only, won't compete with games for the GPU)
```

`install.ps1` writes `config.toml` to `$env:USERPROFILE\.config\sort-sys-alpha\config.toml`
if one doesn't already exist (pass `-ConfigPath` to put it elsewhere). It won't touch an existing config. Edit it, then try a dry run before trusting the scheduled task:

```powershell
uv run sort-sys-alpha plan      # writes plan.json + report.md, touches nothing in source
uv run sort-sys-alpha apply     # executes that plan
```

### Config essentials


```toml
source = "~/Downloads"
dest = "~/Downloads/_Filed"
min_age_minutes = 30        # skip anything downloaded more recently than this
confidence_min = 0.75       # below this, hold instead of moving

[model]
backend = "ollama"          # "ollama" | "lemonade"

[roms.dat_files]
# console = path to a local libretro DAT file -- see below
ps2 = "~/dat/ps2.dat"
snes = "~/dat/snes.dat"
```

`--config <path>` overrides the config file on every command; `--source <dir>` overrides just the source folder for one run (e.g. to re-triage an already-filed folder).

### Getting ROM DAT files (optional, for exact titles)

Without a DAT file configured for a console, a ROM/disc still gets filed correctly, it just keeps its original filename (or the ISO volume label) instead of its canonical title. DAT files come from [libretro-database](https://github.com/libretro/libretro-database)'s `metadat/developer/` folder, grab only the ones you want:

```powershell
mkdir dat-files -Force
$base = "https://raw.githubusercontent.com/libretro/libretro-database/master/metadat/developer"
Invoke-WebRequest "$base/Sony%20-%20PlayStation%202.dat" -OutFile "dat-files\ps2.dat"
Invoke-WebRequest "$base/Nintendo%20-%20Super%20Nintendo%20Entertainment%20System.dat" -OutFile "dat-files\snes.dat"
```

Then point `[roms.dat_files]` at them (see above). PS1/PS2/PSP are matched by the disc's own serial (read straight from `SYSTEM.CNF`, no hashing); cartridge consoles are matched by a CRC32 of the whole ROM file. Both are *title* lookups, not No-Intro/Redump dump verification.

## CLI reference

```
sort-sys-alpha scan [--source DIR]  # inventory + evidence only, no model
sort-sys-alpha plan [--source DIR]  # produce plan.json + report.md
sort-sys-alpha apply [--plan FILE]  # execute a plan
sort-sys-alpha run [--source DIR]   # plan + apply with gates (scheduler entry point)
sort-sys-alpha undo [RUN_ID|last]   # revert a run via the move journal
sort-sys-alpha eval                 # score the labeled fixture set against the LLM tier
sort-sys-alpha doctor               # check model server reachability, config, permissions
sort-sys-alpha prune                # remove empty folders under source, recursively (ADR 0006)
sort-sys-alpha rename [--path DIR]  # recompute names for already-filed files, never recategorizes (ADR 0012)
```

Every command accepts `--config <path>`.

## Development

```sh
uv sync --all-groups
uv run sort-sys-alpha --help
uv run pytest
uv run ruff check .
```

