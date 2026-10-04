import tomllib
from pathlib import Path

import pytest

from sort_sys_alpha.config import Config, load_config


def test_defaults() -> None:
    config = Config()
    assert config.dest == Path("~/Downloads/_Filed").expanduser()
    assert config.confidence_min == 0.75
    assert "Installers" in config.folders.allow
    assert config.model.base_url.startswith("http://localhost")


def test_rejects_non_loopback_model_url() -> None:
    with pytest.raises(ValueError, match="loopback"):
        Config(model={"base_url": "http://example.com/api/v1"})


def test_allow_remote_permits_non_loopback() -> None:
    config = Config(model={"base_url": "http://example.com/api/v1", "allow_remote": True})
    assert config.model.base_url == "http://example.com/api/v1"


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


def test_sample_config_in_plan_is_valid_toml() -> None:
    sample = """
source = "~/Downloads"
dest = "~/Downloads/_Filed"
min_age_minutes = 30
confidence_min = 0.75

[model]
base_url = "http://localhost:8000/api/v1"
name = "Qwen3.5-9B-GGUF"
vision = true
timeout_s = 120
allow_remote = false

[folders]
allow = ["Installers", "Other"]

[[rules]]
match = { true_type = ["application/x-msdownload", "application/x-msi"] }
folder = "Installers"
"""
    data = tomllib.loads(sample)
    config = Config.model_validate(data)
    assert config.rules[0].folder == "Installers"
