# sort-sys-alpha

A local-LLM file sorter for Windows Downloads folders. Figures out what a
file is, gives it a descriptive name, and files it into a fixed set of
folders — never deleting, never moving anything it isn't confident about.

See [`PLAN.md`](PLAN.md) for the full design and milestones, and
[`CLAUDE.md`](CLAUDE.md) for the rules this codebase is built under.

## Status

Planning / early scaffolding (M0). Nothing here moves files yet.

## Development

```sh
uv sync --all-groups
uv run sort-sys-alpha --help
uv run pytest
uv run ruff check .
```

Developed on Linux, targets Windows 11. CI runs the test suite on both
`ubuntu-latest` and `windows-latest`.
