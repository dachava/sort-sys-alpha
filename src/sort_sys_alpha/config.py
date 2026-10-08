"""Config schema and loading for sort-sys-alpha.

See PLAN.md section 7 for the config.toml shape, section 2 for the
"local only" and "nothing moves unless confident" rules this module enforces,
and ADR 0002 for why the scheduled run supports both an `auto` and a `plan`
mode instead of a single fixed behavior.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}

# Lives here, not in scan.py, so low-level modules (feedback.py) that need it
# don't have to import through scan.py's route.py -> llm/ -> feedback.py
# chain and create a cycle. scan.py re-exports it for its existing callers.
STATE_DIR_NAME = ".sort-sys-alpha"

DEFAULT_CONSOLES = [
    "nes", "snes", "n64", "gb", "gbc", "gba", "nds", "fds", "gc", "wii",
    "psx", "ps2", "psp", "genesis", "saturn", "dreamcast", "pcenginecd", "msx",
]

DEFAULT_FOLDERS = [
    "Images",
    "Audio",
    "Documents",
    "Documents/Notes",
    "Documents/Logs",
    "ROMs/<console>",
    "ISOs",
    "Archives",
    "Installers",
    "Other",
]


class ScheduleConfig(BaseModel):
    mode: Literal["auto", "plan"] = "auto"
    notify: bool = True


class OllamaConfig(BaseModel):
    base_url: str = "http://localhost:11434"
    name: str = "qwen2.5vl:7b"
    num_ctx: int = 8192
    keep_alive: str = "2m"


class LemonadeConfig(BaseModel):
    base_url: str = "http://localhost:13305/api/v1"
    name: str = ""


class ModelConfig(BaseModel):
    backend: Literal["ollama", "lemonade"] = "ollama"
    vision: Literal["auto"] | bool = "auto"
    timeout_s: float = 120.0
    allow_remote: bool = False
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    lemonade: LemonadeConfig = Field(default_factory=LemonadeConfig)

    @property
    def active_base_url(self) -> str:
        return self.ollama.base_url if self.backend == "ollama" else self.lemonade.base_url


class RuleMatch(BaseModel):
    true_type: list[str] = Field(default_factory=list)
    ext: list[str] = Field(default_factory=list)
    source_host: list[str] = Field(default_factory=list)


class Rule(BaseModel):
    match: RuleMatch
    folder: str


class FoldersConfig(BaseModel):
    allow: list[str] = Field(default_factory=lambda: list(DEFAULT_FOLDERS))


class RomsConfig(BaseModel):
    consoles: list[str] = Field(default_factory=lambda: list(DEFAULT_CONSOLES))
    # Console -> local DAT file path, for exact-title matching (PLAN.md M7,
    # ADR 0007). A console with no entry here just keeps today's behavior
    # (volume label as the name hint).
    dat_files: dict[str, Path] = Field(default_factory=dict)

    @field_validator("dat_files", mode="before")
    @classmethod
    def _expand_dat_paths(cls, value: dict[str, str] | None) -> dict[str, str]:
        if not value:
            return {}
        return {console: str(Path(path).expanduser()) for console, path in value.items()}


class SubfoldersConfig(BaseModel):
    mode: Literal["hybrid"] = "hybrid"
    max_depth: int = 4
    max_files: int = 500


class NamingConfig(BaseModel):
    """Per-category naming templates. Keys other than `default` are category
    names (e.g. `Images`, `ROMs`) mapped to a template string; see PLAN.md
    section 4.8. The actual per-category templates are still an open decision
    (PLAN.md section 11), so arbitrary category keys are accepted as-is.
    """

    model_config = ConfigDict(extra="allow")

    default: str = "{date}_{slug}"

    def template_for(self, category: str) -> str:
        return getattr(self, category, None) or (self.model_extra or {}).get(category, self.default)


class Config(BaseModel):
    source: Path = Field(default_factory=lambda: Path("~/Downloads").expanduser())
    dest: Path = Field(default_factory=lambda: Path("~/Downloads/_Filed").expanduser())
    min_age_minutes: int = 30
    confidence_min: float = 0.75
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    folders: FoldersConfig = Field(default_factory=FoldersConfig)
    roms: RomsConfig = Field(default_factory=RomsConfig)
    rules: list[Rule] = Field(default_factory=list)
    subfolders: SubfoldersConfig = Field(default_factory=SubfoldersConfig)
    naming: NamingConfig = Field(default_factory=NamingConfig)

    @field_validator("source", "dest", mode="before")
    @classmethod
    def _expand(cls, value: str | Path) -> Path:
        return Path(value).expanduser()

    def model_post_init(self, __context) -> None:
        self._check_model_locality()

    def _check_model_locality(self) -> None:
        if self.model.allow_remote:
            return
        base_url = self.model.active_base_url
        host = urlparse(base_url).hostname
        if host not in LOOPBACK_HOSTS:
            raise ValueError(
                f"model.{self.model.backend}.base_url '{base_url}' is not a loopback "
                f"address (host={host!r}). File contents must stay on this machine; "
                "set model.allow_remote = true to override for development."
            )

    def resolved_folder_allowlist(self) -> set[str]:
        """Expand the `ROMs/<console>` placeholder into one entry per configured console."""
        resolved: set[str] = set()
        for folder in self.folders.allow:
            if folder == "ROMs/<console>":
                resolved.update(f"ROMs/{console}" for console in self.roms.consoles)
            else:
                resolved.add(folder)
        return resolved


def default_config_path() -> Path:
    return Path("~/.config/sort-sys-alpha/config.toml").expanduser()


def load_config(path: Path | None = None) -> Config:
    """Load config from `path`, or return defaults if it doesn't exist."""
    candidate = path or default_config_path()
    if not candidate.exists():
        return Config()
    raw = candidate.read_bytes()
    # Windows editors (Notepad, PowerShell's `-Encoding utf8`, which -- unlike
    # PowerShell 7+ -- writes a BOM on Windows PowerShell 5.1) commonly emit a
    # UTF-8 BOM. tomllib treats a BOM as invalid syntax rather than stripping
    # it, so do that ourselves before parsing.
    raw = raw.removeprefix(b"\xef\xbb\xbf")
    data = tomllib.loads(raw.decode("utf-8"))
    return Config.model_validate(data)
