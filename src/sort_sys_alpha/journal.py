"""The move journal (journal.jsonl): every move, written before it executes,
so `undo` is always possible. See PLAN.md section 4.10.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from .config import Config
from .movefs import move_path
from .scan import STATE_DIR_NAME

JOURNAL_FILENAME = "journal.jsonl"


class JournalEntry(BaseModel):
    run_id: str
    timestamp: datetime
    source: Path
    target: Path


def _journal_path(config: Config) -> Path:
    return config.dest / STATE_DIR_NAME / JOURNAL_FILENAME


def append_entry(source: Path, target: Path, run_id: str, config: Config) -> None:
    entry = JournalEntry(run_id=run_id, timestamp=datetime.now(UTC), source=source, target=target)
    path = _journal_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(entry.model_dump_json() + "\n")


def read_entries(config: Config) -> list[JournalEntry]:
    path = _journal_path(config)
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(JournalEntry.model_validate(json.loads(line)))
    return entries


def last_run_id(config: Config) -> str | None:
    entries = read_entries(config)
    return entries[-1].run_id if entries else None


def undo_run(run_id: str, config: Config) -> list[str]:
    """Reverse every move for `run_id`, most recent first. Returns a message per entry."""
    entries = [e for e in read_entries(config) if e.run_id == run_id]
    messages: list[str] = []

    for entry in reversed(entries):
        if not entry.target.exists():
            messages.append(f"skip: {entry.target} no longer exists")
            continue
        if entry.source.exists():
            messages.append(f"skip: {entry.source} already exists, not overwriting")
            continue
        move_path(entry.target, entry.source)
        messages.append(f"restored {entry.target} -> {entry.source}")

    return messages
