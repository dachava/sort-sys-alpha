"""Subfolder classification: unit / grab-bag / unsure. See PLAN.md section
4.2b. Only the deterministic-marker path is implemented here — the model
only gets involved (PLAN.md: "the model gets a listing... and only decides
when markers don't settle it") once the LLM tier exists (M3); until then,
a folder with no clear marker is a grab-bag (split), and genuinely
conflicting signals are held as "unsure" rather than guessed at.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .groups import detect_groups
from .identify import build_evidence
from .items import FolderUnit, ScanItem
from .route import route

CODE_PROJECT_MARKER_NAMES = {".git", "package.json", "pyproject.toml"}
EXTRACTED_APP_MARKER_NAME = "setup.exe"
# A portable tool (chdman, ffmpeg, ...) ships as one or more .exe plus
# helper scripts, no .dll and no installer -- still "data needed for
# execution" that has to move as one folder, same as an app with .dll.
EXTRACTED_APP_COMPANION_EXTENSIONS = {".dll", ".bat", ".cmd"}
ALBUM_AUDIO_EXTENSIONS = {".mp3", ".flac", ".ogg", ".wav", ".m4a", ".aac", ".wma"}
# ".cue" deliberately excluded: it pairs with either audio tracks (an album,
# handled by _has_album_markers) or binary tracks (a disc dump) — treating it
# as its own disc signal would flag every album as a conflicting "unsure".
# ".gdi"/".m3u"/".ccd" have no legitimate non-disc use, so finding one and
# failing to identify a console is still a real "disc dump, unsure"
# situation worth holding the whole folder over. ".iso"/".bin"/".img" don't
# get that trust: those extensions cover plenty of ordinary non-disc files
# (a save file next to a cartridge ROM, a V8 snapshot blob in an extracted
# browser build...), so on their own they're not treated as a disc signal
# at all -- only as something _disc_console_category tries, same as the
# sheet extensions. See _has_disc_sheet / _has_ambiguous_disc_extension.
# ".cue" deliberately excluded from DISC_SHEET_EXTENSIONS: it pairs with
# either audio tracks (an album, handled by _has_album_markers) or binary
# tracks (a disc dump) -- treating it as its own disc signal would flag
# every album as a conflicting "unsure". It's still tried for console
# identification below, same as the others.
DISC_SHEET_EXTENSIONS = {".gdi", ".m3u", ".ccd"}
AMBIGUOUS_DISC_EXTENSIONS = {".iso", ".bin", ".img"}
DISC_IDENTIFY_EXTENSIONS = DISC_SHEET_EXTENSIONS | AMBIGUOUS_DISC_EXTENSIONS | {".cue"}


@dataclass(frozen=True)
class Classification:
    verdict: str  # "unit" | "grab_bag" | "unsure" | "limit"
    category: str | None
    reason: str
    suggest_delete: bool = False


def _direct_entries(root: Path) -> list[Path]:
    try:
        return sorted(root.iterdir())
    except OSError:
        return []


def _walk_file_count_and_depth(root: Path, max_depth: int) -> tuple[int, int]:
    file_count = 0
    deepest = 0
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack:
        current, depth = stack.pop()
        if depth > max_depth:
            deepest = max(deepest, depth)
            continue
        for entry in _direct_entries(current):
            if entry.is_dir():
                stack.append((entry, depth + 1))
            else:
                file_count += 1
                deepest = max(deepest, depth)
    return file_count, deepest


def _has_code_project_markers(entries: list[Path]) -> bool:
    names = {p.name for p in entries}
    if names & CODE_PROJECT_MARKER_NAMES:
        return True
    return any(p.is_file() and p.suffix.lower() == ".tf" for p in entries)


def _has_extracted_app_markers(entries: list[Path]) -> bool:
    files = [p for p in entries if p.is_file()]
    if any(p.name.lower() == EXTRACTED_APP_MARKER_NAME for p in files):
        return True
    exts = {p.suffix.lower() for p in files}
    return ".exe" in exts and bool(exts & EXTRACTED_APP_COMPANION_EXTENSIONS)


def _has_album_markers(entries: list[Path]) -> bool:
    exts = {p.suffix.lower() for p in entries if p.is_file()}
    return bool(exts & ALBUM_AUDIO_EXTENSIONS) and ".cue" in exts


def _has_disc_sheet(entries: list[Path]) -> bool:
    exts = {p.suffix.lower() for p in entries if p.is_file()}
    return bool(exts & DISC_SHEET_EXTENSIONS)


def _has_ambiguous_disc_extension(entries: list[Path]) -> bool:
    exts = {p.suffix.lower() for p in entries if p.is_file()}
    return bool(exts & AMBIGUOUS_DISC_EXTENSIONS)


def _disc_console_category(entries: list[Path], config: Config) -> str | None:
    for path in entries:
        if path.is_file() and path.suffix.lower() in DISC_IDENTIFY_EXTENSIONS:
            verdict = route(build_evidence(path), config)
            if verdict is not None and verdict.category.startswith("ROMs/"):
                return verdict.category
    return None


def _single_builtin_category(files: list[Path], config: Config) -> tuple[str, bool] | None:
    """`(category, suggest_delete)` when every file routes to the same
    rule-tier category -- `suggest_delete` is only True when every member's
    own verdict agreed on that too, so the whole folder isn't flagged for
    deletion review on the strength of just one junk file among others.
    """
    if not files:
        return None
    verdicts = []
    for path in files:
        verdict = route(build_evidence(path), config)
        if verdict is None:
            return None
        verdicts.append(verdict)
        if len({v.category for v in verdicts}) > 1:
            return None
    return verdicts[0].category, all(v.suggest_delete for v in verdicts)


def classify_subfolder(root: Path, config: Config) -> Classification:
    file_count, depth = _walk_file_count_and_depth(root, config.subfolders.max_depth)
    if file_count > config.subfolders.max_files or depth > config.subfolders.max_depth:
        return Classification("limit", None, "exceeds subfolder depth/size limits")

    entries = _direct_entries(root)
    if not entries:
        return Classification("grab_bag", None, "empty folder")

    # A positively identified console disc dump is checked first and wins
    # outright, rather than joining the generic signals below as one more
    # thing that could "conflict" -- a romhack release routinely bundles a
    # small patcher .exe + .bat alongside the actual disc dump, and that
    # incidental extracted-app marker shouldn't make a successfully
    # identified ROM/console folder ambiguous.
    has_disc_sheet = _has_disc_sheet(entries)
    if has_disc_sheet or _has_ambiguous_disc_extension(entries):
        console_category = _disc_console_category(entries, config)
        if console_category:
            return Classification("unit", console_category, "disc/game dump, console identified")
        if has_disc_sheet:
            return Classification("unsure", None, "disc/game dump, console not determined")

    signals: list[tuple[str, str]] = []
    if _has_code_project_markers(entries):
        signals.append(("Other", "code project markers"))
    if _has_extracted_app_markers(entries):
        signals.append(("Installers", "extracted app markers"))
    if _has_album_markers(entries):
        signals.append(("Audio", "album markers (audio + cue sheet)"))

    if len(signals) > 1:
        reasons = ", ".join(reason for _category, reason in signals)
        return Classification("unsure", None, f"conflicting markers: {reasons}")
    if len(signals) == 1:
        category, reason = signals[0]
        return Classification("unit", category, reason)

    files = [p for p in entries if p.is_file()]
    has_subdirs = any(p.is_dir() for p in entries)
    # Require >= 2 files: a single file trivially satisfies "only one type",
    # but wrapping one lone file in a whole-folder move isn't what "a folder
    # of only one type" (PLAN.md 4.2b) means — that's just a grab-bag of one.
    if not has_subdirs and len(files) >= 2:
        result = _single_builtin_category(files, config)
        if result:
            category, suggest_delete = result
            return Classification(
                "unit", category, "single-type folder", suggest_delete=suggest_delete
            )

    return Classification("grab_bag", None, "mixed contents, no project/app markers")


def process_subfolder(
    root: Path, config: Config
) -> tuple[list[ScanItem], list[tuple[Path, str]], list[Path]]:
    """Returns (items ready for identify/route/gate, (path, reason) whole-folder
    holds, and every folder that was split as a grab-bag — the caller needs
    that list to check post-apply whether any of them ended up empty, since
    an emptied folder is reported as a suggested deletion, never removed).
    """
    classification = classify_subfolder(root, config)

    if classification.verdict == "unit":
        members = tuple(sorted(p for p in root.rglob("*") if p.is_file()))
        unit = FolderUnit(
            root,
            classification.category,
            classification.reason,
            members,
            classification.suggest_delete,
        )
        return [unit], [], []

    if classification.verdict in ("unsure", "limit"):
        return [], [(root, classification.reason)], []

    # grab_bag: split -- files become normal candidates, subfolders recurse.
    items: list[ScanItem] = []
    held: list[tuple[Path, str]] = []
    grab_bag_dirs: list[Path] = [root]
    entries = _direct_entries(root)

    files = [p for p in entries if p.is_file() and not p.name.startswith(".")]
    items.extend(detect_groups(files))

    for entry in entries:
        if entry.is_dir() and not entry.name.startswith("."):
            sub_items, sub_held, sub_grab_bags = process_subfolder(entry, config)
            items.extend(sub_items)
            held.extend(sub_held)
            grab_bag_dirs.extend(sub_grab_bags)

    return items, held, grab_bag_dirs
