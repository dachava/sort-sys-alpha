"""Move primitives shared by `apply` and `undo`. See PLAN.md section 4.7:
same-volume rename where possible; otherwise copy, verify, then remove the
source (the only "delete" in the system, and it's part of a move).
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path


class MoveVerificationError(Exception):
    pass


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_tree(root: Path) -> str:
    """One hash over every file under root: path relative to root, then content."""
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(hash_file(path).encode())
    return digest.hexdigest()


def unique_target(target: Path) -> Path:
    """`target`, or `target` with a -2, -3, ... suffix if it already exists."""
    if not target.exists():
        return target
    stem, ext = target.stem, target.suffix
    n = 2
    while True:
        candidate = target.with_name(f"{stem}-{n}{ext}")
        if not candidate.exists():
            return candidate
        n += 1


def move_path(source: Path, target: Path) -> None:
    """Move a file or a whole directory tree from source to target."""
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        source.rename(target)
        return
    except OSError:
        pass  # likely cross-volume; fall through to copy + verify + remove

    if source.is_dir():
        before = hash_tree(source)
        shutil.copytree(source, target)
        after = hash_tree(target)
        if before != after:
            shutil.rmtree(target, ignore_errors=True)
            raise MoveVerificationError(f"hash mismatch copying directory {source} -> {target}")
        shutil.rmtree(source)
    else:
        before = hash_file(source)
        shutil.copy2(source, target)
        after = hash_file(target)
        if before != after:
            target.unlink(missing_ok=True)
            raise MoveVerificationError(f"hash mismatch copying {source} -> {target}")
        source.unlink()
