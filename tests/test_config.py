import tomllib
from pathlib import Path

import pytest

from sort_sys_alpha.config import Config, load_config


def test_defaults() -> None:
    config = Config()
    assert config.dest == Path("~/Downloads/_Filed").expanduser()
    assert config.confidence_min == 0.75
    assert "ROMs/<console>" in config.folders.allow
    assert config.model.backend == "ollama"
    assert config.model.active_base_url.startswith("http://localhost")
    assert config.schedule.mode == "auto"


def test_rejects_non_loopback_active_backend_url() -> None:
    with pytest.raises(ValueError, match="loopback"):
        Config(model={"backend": "ollama", "ollama": {"base_url": "http://example.com"}})


def test_only_checks_the_active_backend() -> None:
    # lemonade.base_url is irrelevant while backend == "ollama".
    config = Config(
        model={
            "backend": "ollama",
            "ollama": {"base_url": "http://localhost:11434"},
            "lemonade": {"base_url": "http://example.com/api/v1"},
        }
    )
    assert config.model.active_base_url == "http://localhost:11434"


def test_allow_remote_permits_non_loopback() -> None:
    config = Config(
        model={
            "backend": "lemonade",
            "lemonade": {"base_url": "http://example.com/api/v1"},
            "allow_remote": True,
        }
    )
    assert config.model.active_base_url == "http://example.com/api/v1"


def test_resolved_folder_allowlist_expands_rom_consoles() -> None:
    config = Config()
    resolved = config.resolved_folder_allowlist()
    assert "ROMs/<console>" not in resolved
    assert "ROMs/snes" in resolved
    assert "ROMs/ps2" in resolved
    assert "Images" in resolved


def test_load_missing_path_returns_defaults(tmp_path: Path) -> None:
    config = load_config(tmp_path / "does-not-exist.toml")
    assert config == Config()


def test_load_from_file(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        'source = "~/Downloads"\n'
        'dest = "~/Downloads/_Filed"\n'
        "confidence_min = 0.9\n"
    )
    config = load_config(config_path)
    assert config.confidence_min == 0.9


def test_load_strips_a_leading_utf8_bom(tmp_path: Path) -> None:
    # Windows PowerShell 5.1's `-Encoding utf8` (and some editors' "UTF-8"
    # save option) writes a BOM, which tomllib otherwise rejects outright.
    config_path = tmp_path / "config.toml"
    config_path.write_bytes(b"\xef\xbb\xbf" + b'confidence_min = 0.9\n')
    config = load_config(config_path)
    assert config.confidence_min == 0.9


def test_sample_config_in_plan_is_valid_toml() -> None:
    sample = """
source = "~/Downloads"
dest = "~/Downloads/_Filed"
min_age_minutes = 30
confidence_min = 0.75

[schedule]
mode = "auto"
notify = true

[model]
backend = "ollama"
vision = "auto"
timeout_s = 120
allow_remote = false

[model.ollama]
base_url = "http://localhost:11434"
name = "qwen2.5vl:7b"
num_ctx = 8192
keep_alive = "2m"

[model.lemonade]
base_url = "http://localhost:13305/api/v1"
name = ""

[folders]
allow = ["Images", "Audio", "Documents", "Documents/Notes", "Documents/Logs",
         "ROMs/<console>", "ISOs", "Archives", "Installers", "Other"]

[roms]
consoles = ["nes", "snes", "n64", "gb", "gbc", "gba", "nds", "gc", "wii",
            "psx", "ps2", "psp", "genesis", "saturn", "dreamcast"]

[[rules]]
match = { ext = [".txt", ".md"] }
folder = "Documents/Notes"

[[rules]]
match = { ext = [".log"] }
folder = "Documents/Logs"

[[rules]]
match = { true_type = ["application/x-msdownload", "application/x-msi"] }
folder = "Installers"

[subfolders]
mode = "hybrid"
max_depth = 4
max_files = 500
"""
    data = tomllib.loads(sample)
    config = Config.model_validate(data)
    assert config.rules[0].folder == "Documents/Notes"
    assert "ROMs/dreamcast" in config.resolved_folder_allowlist()
