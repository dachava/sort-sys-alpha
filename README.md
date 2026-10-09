# sort-sys-alpha

A local-LLM file sorter for a Windows Downloads folder. Figures out what a
file is, gives it a descriptive name, and files it into a fixed set of
folders — never deleting, never moving anything it isn't confident about.
Deterministic rules settle almost everything; a local LLM (nothing ever
leaves the machine) only handles what the rules can't.

This is the runbook: how to set it up, how to run it day to day, and what
to do when something looks wrong. For the full design story, see
[`docs/how-it-works.md`](docs/how-it-works.md) and
[`docs/module-reference.md`](docs/module-reference.md); for the spec and
decision history, [`PLAN.md`](PLAN.md) and [`docs/adr/`](docs/adr/).

## One-time setup (Windows)

```powershell
git clone <this repo's URL>
cd sort-sys-alpha
.\scripts\windows\install.ps1          # installs uv, syncs the env, writes a default config.toml
.\scripts\windows\register-task.ps1    # registers the weekly Scheduled Task (idle-only, won't compete with games for the GPU)
```

`install.ps1` writes `config.toml` to
`$env:USERPROFILE\.config\sort-sys-alpha\config.toml` if one doesn't
already exist (pass `-ConfigPath` to put it elsewhere) — it never touches
an existing config. `register-task.ps1` is optional: skip it if you'd
rather run everything manually.

## Config

Lives at `$HOME\.config\sort-sys-alpha\config.toml`. The fields you'll
actually touch:

```toml
source = "~/Downloads"
dest = "~/Downloads/_Filed"
min_age_minutes = 30        # skip anything downloaded more recently than this
confidence_min = 0.75       # below this, hold instead of moving

[model]
backend = "ollama"          # "ollama" | "lemonade"

[roms.dat_files]
# console = path to a local libretro DAT file -- see "Adding a DAT file" below
ps2 = "~/dat/ps2.dat"
snes = "~/dat/snes.dat"

[naming]
# default is "{title}" (human-readable, no date prefix) for every category.
# Override one explicitly if you want something else, e.g. a plain
# hyphenated slug for installers:
Installers = "{slug}"
```

### Adding a DAT file (for exact ROM/disc titles)

Without one configured for a console, a ROM/disc still files correctly —
it just keeps its original filename instead of its canonical title. DAT
files come from
[libretro-database](https://github.com/libretro/libretro-database)'s
`metadat/developer/` folder; grab only the ones you want:

```powershell
mkdir dat-files -Force
$base = "https://raw.githubusercontent.com/libretro/libretro-database/master/metadat/developer"
Invoke-WebRequest "$base/Sony%20-%20PlayStation%202.dat" -OutFile "dat-files\ps2.dat"
Invoke-WebRequest "$base/Nintendo%20-%20Super%20Nintendo%20Entertainment%20System.dat" -OutFile "dat-files\snes.dat"
```

Then add the matching line under `[roms.dat_files]` above. PS1/PS2/PSP
are matched by the disc's own serial (read from `SYSTEM.CNF`); cartridge
consoles (NES, SNES, Genesis, GBA, N64, GB/GBC, FDS, Game Gear, Master
System, 32X, SG-1000) are matched by a CRC32 of the ROM file — including
one sitting inside a single-game zip/7z, not just loose files.

## Day-to-day usage

**Normal flow** — review before anything moves:
```powershell
uv run sort-sys-alpha plan      # writes report.md, touches nothing in source
# read report.md
uv run sort-sys-alpha apply     # executes that plan
```
If `register-task.ps1` is set up, this already happens weekly on its own
(`schedule.mode` in config picks `auto`, which also applies, or `plan`,
which stops after reviewing and notifies you).

**Something didn't sort right and you've since fixed detection for it**
(new DAT file, newly-supported console, a bug fix) — re-check an
already-filed folder against today's rules without touching anything else:
```powershell
uv run sort-sys-alpha plan --source "$HOME\Downloads\_Filed\Archives"
uv run sort-sys-alpha apply --plan "$HOME\Downloads\_Filed\.sort-sys-alpha\plan-Archives.json"
```

**Names look stale** (e.g. after changing a naming convention, or a new
DAT match exists for something already filed) — recompute names without
moving anything between folders:
```powershell
uv run sort-sys-alpha rename
# or scope it: uv run sort-sys-alpha rename --path "$HOME\Downloads\_Filed\Documents"
# review report-rename.md, then:
uv run sort-sys-alpha apply --plan "$HOME\Downloads\_Filed\.sort-sys-alpha\plan-rename.json"
```

**Leftover empty folders in Downloads** (after a grab-bag folder got split
and emptied out):
```powershell
uv run sort-sys-alpha prune
```

**Something moved that shouldn't have**:
```powershell
uv run sort-sys-alpha undo          # reverts the most recent run
uv run sort-sys-alpha undo <run_id> # or a specific one -- see journal.jsonl
```

**Model server not responding, or want to sanity-check the setup**:
```powershell
uv run sort-sys-alpha doctor
```

## CLI reference

```
sort-sys-alpha scan [--source DIR]  # inventory + evidence only, no model
sort-sys-alpha plan [--source DIR]  # produce plan.json + report.md
sort-sys-alpha apply [--plan FILE]  # execute a plan
sort-sys-alpha run [--source DIR]   # plan + apply with gates (scheduler entry point)
sort-sys-alpha undo [RUN_ID|last]   # revert a run via the move journal
sort-sys-alpha eval                 # score the labeled fixture set against the LLM tier
sort-sys-alpha doctor               # check model server reachability, config, permissions
sort-sys-alpha prune                # remove empty folders under source, recursively
sort-sys-alpha rename [--path DIR]  # recompute names for already-filed files, never recategorizes
```

Every command accepts `--config <path>` if your config isn't at the
default location.

## Development

```sh
uv sync --all-groups
uv run sort-sys-alpha --help
uv run pytest
uv run ruff check .
```

Developed on Linux, targets Windows 11 — the full suite runs in CI on
both `ubuntu-latest` and `windows-latest` with no real Windows box needed
for tests.
