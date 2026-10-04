import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sort_sys_alpha.config import Config
from sort_sys_alpha.identify.types import Evidence
from sort_sys_alpha.llm.backend import (
    LlmError,
    OllamaBackend,
    OpenAICompatBackend,
    backend_for,
    describe_backend,
)


def _evidence() -> Evidence:
    return Evidence(
        path=Path("mystery.xyz"),
        original_name="mystery.xyz",
        extension=".xyz",
        size=10,
        created=datetime.now(UTC),
        modified=datetime.now(UTC),
    )


def _config(base_url: str, *, backend: str = "ollama", timeout_s: float | None = None) -> Config:
    model: dict = {"backend": backend, backend: {"base_url": base_url, "name": "test-model"}}
    if timeout_s is not None:
        model["timeout_s"] = timeout_s
    return Config.model_validate({"model": model})


def _verdict_json(**overrides) -> str:
    data = {
        "kind": "router manual",
        "category": "Documents",
        "name": "my-doc",
        "confidence": 0.9,
        "reason": "looks like a manual",
    }
    data.update(overrides)
    return json.dumps(data)


def test_ollama_backend_parses_a_valid_reply(fake_llm_server) -> None:
    fake_llm_server.set_ollama_reply(_verdict_json())
    config = _config(fake_llm_server.base_url)

    verdict = OllamaBackend().classify(_evidence(), config)
    assert verdict.category == "Documents"
    assert verdict.confidence == 0.9
    assert verdict.suggest_delete is False


def test_ollama_backend_strips_think_blocks(fake_llm_server) -> None:
    content = "<think>hmm, let me consider this one</think>" + _verdict_json(category="Other")
    fake_llm_server.set_ollama_reply(content)
    config = _config(fake_llm_server.base_url)

    verdict = OllamaBackend().classify(_evidence(), config)
    assert verdict.category == "Other"


def test_backend_raises_on_invalid_json(fake_llm_server) -> None:
    fake_llm_server.set_ollama_reply("not json at all")
    config = _config(fake_llm_server.base_url)

    with pytest.raises(LlmError):
        OllamaBackend().classify(_evidence(), config)


def test_backend_raises_on_schema_mismatch(fake_llm_server) -> None:
    fake_llm_server.set_ollama_reply(json.dumps({"category": "Documents"}))  # missing fields
    config = _config(fake_llm_server.base_url)

    with pytest.raises(LlmError):
        OllamaBackend().classify(_evidence(), config)


def test_backend_raises_on_http_error(fake_llm_server) -> None:
    fake_llm_server.set_raw_reply({"error": "boom"}, status=500)
    config = _config(fake_llm_server.base_url)

    with pytest.raises(LlmError):
        OllamaBackend().classify(_evidence(), config)


def test_backend_raises_when_unreachable() -> None:
    config = _config("http://127.0.0.1:1")  # nothing listens here
    with pytest.raises(LlmError):
        OllamaBackend().classify(_evidence(), config)


def test_backend_raises_on_timeout(fake_llm_server) -> None:
    fake_llm_server.set_ollama_reply(_verdict_json(), delay=0.5)
    config = _config(fake_llm_server.base_url, timeout_s=0.05)

    with pytest.raises(LlmError):
        OllamaBackend().classify(_evidence(), config)


def test_openai_compat_backend_parses_a_valid_reply(fake_llm_server) -> None:
    fake_llm_server.set_openai_reply(_verdict_json())
    config = _config(fake_llm_server.base_url, backend="lemonade")

    verdict = OpenAICompatBackend().classify(_evidence(), config)
    assert verdict.category == "Documents"


def test_backend_for_dispatches_on_config() -> None:
    assert isinstance(backend_for(Config()), OllamaBackend)
    config = Config.model_validate({"model": {"backend": "lemonade"}})
    assert isinstance(backend_for(config), OpenAICompatBackend)


def test_describe_backend_reports_reachable_and_model_found(fake_llm_server) -> None:
    fake_llm_server.set_raw_reply({"models": [{"name": "test-model"}]})
    config = _config(fake_llm_server.base_url)

    lines = describe_backend(config)
    assert any("reachable" in line for line in lines)
    assert any("found" in line for line in lines)


def test_describe_backend_reports_unreachable() -> None:
    config = _config("http://127.0.0.1:1")
    lines = describe_backend(config)
    assert any("NOT reachable" in line for line in lines)
