# sort-sys-alpha

A local-LLM file sorter for Windows Downloads folders. Figures out what a
file is, gives it a descriptive name, and files it into a fixed set of
folders — never deleting, never moving anything it isn't confident about.

See [`PLAN.md`](PLAN.md) for the full design and milestones, and
[`CLAUDE.md`](CLAUDE.md) for the rules this codebase is built under.

## Status

M4 landed: scan, identify, rules + LLM routing, gate, plan/apply/undo,
subfolder handling, and the scheduled `run` command (auto/plan modes +
toast notifications) are all implemented. See PLAN.md section 10 for what's
still ahead (feedback loop, eval, vision, ROM DAT matching, naming
templates).

## Development

```sh
uv sync --all-groups
uv run sort-sys-alpha --help
uv run pytest
uv run ruff check .
```

Developed on Linux, targets Windows 11. CI runs the test suite on both
`ubuntu-latest` and `windows-latest`.
