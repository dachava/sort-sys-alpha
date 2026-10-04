"""Config schema and loading for sort-sys-alpha.

See PLAN.md section 7 for the config.toml shape and section 2 for the
"local only" and "nothing moves unless confident" rules this module enforces.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}

DEFAULT_FOLDERS = [
    "Installers",
    "Disk Images",
    "Screenshots",
    "Photos",
    "Receipts & Invoices",
    "Bank & Finance",
    "Work",
    "Personal Documents",
    "Guides & Manuals",
    "Diagrams",
    "Code & Config",
    "Archives",
    "Audio",
    "Video",
    "Fonts",
    "3D Models",
    "Other",
]


class ModelConfig(BaseModel):
    base_url: str = "http://localhost:8000/api/v1"
    name: str = "Qwen3.5-9B-GGUF"
    vision: bool = True
    timeout_s: int = 120
    allow_remote: bool = False


class RuleMatch(BaseModel):
    true_type: list[str] = Field(default_factory=list)
    extension: list[str] = Field(default_factory=list)
    source_host: list[str] = Field(default_factory=list)


class Rule(BaseModel):
    match: RuleMatch
    folder: str


class FoldersConfig(BaseModel):
    allow: list[str] = Field(default_factory=lambda: list(DEFAULT_FOLDERS))


class Config(BaseModel):
    source: Path = Field(default_factory=lambda: Path("~/Downloads").expanduser())
    dest: Path = Field(default_factory=lambda: Path("~/Downloads/_Filed").expanduser())
    min_age_minutes: int = 30
    confidence_min: float = 0.75
    model: ModelConfig = Field(default_factory=ModelConfig)
    folders: FoldersConfig = Field(default_factory=FoldersConfig)
    rules: list[Rule] = Field(default_factory=list)

    @field_validator("source", "dest", mode="before")
    @classmethod
    def _expand(cls, value: str | Path) -> Path:
        return Path(value).expanduser()

    def model_post_init(self, __context) -> None:
        self._check_model_locality()

    def _check_model_locality(self) -> None:
        if self.model.allow_remote:
            return
        host = urlparse(self.model.base_url).hostname
        if host not in LOOPBACK_HOSTS:
            raise ValueError(
                f"model.base_url '{self.model.base_url}' is not a loopback address "
                f"(host={host!r}). File contents must stay on this machine; set "
                "model.allow_remote = true to override for development."
            )


def default_config_path() -> Path:
    return Path("~/.config/sort-sys-alpha/config.toml").expanduser()


def load_config(path: Path | None = None) -> Config:
    """Load config from `path`, or return defaults if it doesn't exist."""
    candidate = path or default_config_path()
    if not candidate.exists():
        return Config()
    with candidate.open("rb") as f:
        data = tomllib.load(f)
    return Config.model_validate(data)
