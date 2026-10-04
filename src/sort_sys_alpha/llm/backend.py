"""Ollama and OpenAI-compatible (Lemonade) chat clients. See PLAN.md section
4.5. Both are a single JSON POST over stdlib `urllib` -- no HTTP dependency
needed for that.

Every failure mode PLAN.md 4.6 lists for the model ("unreachable, times out,
or returns invalid JSON") surfaces as `LlmError`, which `route.resolve()`
turns into a hold reason -- never a crash.
"""

from __future__ import annotations

import json
import re
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import ValidationError

from ..config import Config
from ..feedback import recent_accepted_examples
from ..identify.types import Evidence
from .prompts import build_system_prompt, build_user_message
from .schema import RESPONSE_JSON_SCHEMA, LlmVerdict

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


class LlmError(Exception):
    """The model is unreachable, times out, or returns invalid JSON (PLAN.md 4.6)."""


class Backend(Protocol):
    def classify(self, evidence: Evidence, config: Config) -> LlmVerdict: ...


def _request_json(url: str, timeout_s: float, *, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    method = "POST" if body is not None else "GET"
    request = Request(url, data=data, headers={"Content-Type": "application/json"}, method=method)
    try:
        with urlopen(request, timeout=timeout_s) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as e:
        raise LlmError(f"model server returned HTTP {e.code} calling {url}") from e
    except (URLError, TimeoutError, OSError) as e:
        raise LlmError(f"model unreachable or timed out calling {url}: {e}") from e

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise LlmError(f"model server returned a non-JSON response from {url}: {e}") from e


def _parse_verdict(content: str) -> LlmVerdict:
    stripped = _THINK_RE.sub("", content).strip()
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as e:
        raise LlmError(f"model returned invalid JSON: {e}") from e
    try:
        return LlmVerdict.model_validate(data)
    except ValidationError as e:
        raise LlmError(f"model response failed schema validation: {e}") from e


class OllamaBackend:
    """Native `/api/chat` -- see PLAN.md 4.5 for why not the OpenAI-compatible
    endpoint: schema-constrained `format`, explicit `num_ctx`, `keep_alive`
    to free VRAM, and `think: false` to suppress reasoning-model preambles.
    """

    def classify(self, evidence: Evidence, config: Config) -> LlmVerdict:
        system_prompt = build_system_prompt(config, recent_accepted_examples(config))
        body = {
            "model": config.model.ollama.name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": build_user_message(evidence)},
            ],
            "format": RESPONSE_JSON_SCHEMA,
            "options": {"num_ctx": config.model.ollama.num_ctx},
            "keep_alive": config.model.ollama.keep_alive,
            "think": False,
            "stream": False,
        }
        url = f"{config.model.active_base_url}/api/chat"
        raw = _request_json(url, config.model.timeout_s, body=body)
        try:
            content = raw["message"]["content"]
        except (KeyError, TypeError) as e:
            raise LlmError(f"unexpected Ollama response shape from {url}: {raw!r}") from e
        return _parse_verdict(content)


class OpenAICompatBackend:
    """Lemonade's OpenAI-compatible `/chat/completions`."""

    def classify(self, evidence: Evidence, config: Config) -> LlmVerdict:
        system_prompt = build_system_prompt(config, recent_accepted_examples(config))
        body = {
            "model": config.model.lemonade.name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": build_user_message(evidence)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "sort_sys_alpha_verdict", "schema": RESPONSE_JSON_SCHEMA},
            },
            "stream": False,
        }
        url = f"{config.model.active_base_url}/chat/completions"
        raw = _request_json(url, config.model.timeout_s, body=body)
        try:
            content = raw["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LlmError(f"unexpected Lemonade response shape from {url}: {raw!r}") from e
        return _parse_verdict(content)


def backend_for(config: Config) -> Backend:
    return OllamaBackend() if config.model.backend == "ollama" else OpenAICompatBackend()


def describe_backend(config: Config) -> list[str]:
    """Read-only reachability/model-presence checks for `doctor` (PLAN.md 4.5)."""
    base_url = config.model.active_base_url
    lines = [f"backend: {config.model.backend} ({base_url})"]

    try:
        if config.model.backend == "ollama":
            tags = _request_json(f"{base_url}/api/tags", config.model.timeout_s)
            names = {m.get("name") for m in tags.get("models", [])}
            wanted = config.model.ollama.name
            lines.append(f"reachable, {len(names)} model(s) pulled")
            lines.append(f"model {wanted!r}: {'found' if wanted in names else 'NOT FOUND'}")
            try:
                show = _request_json(
                    f"{base_url}/api/show", config.model.timeout_s, body={"name": wanted}
                )
                has_vision = "vision" in show.get("capabilities", [])
                lines.append(f"vision capability: {'yes' if has_vision else 'no'}")
            except LlmError as e:
                lines.append(f"could not check vision capability: {e}")
        else:
            models = _request_json(f"{base_url}/models", config.model.timeout_s)
            names = {m.get("id") for m in models.get("data", [])}
            wanted = config.model.lemonade.name
            lines.append(f"reachable, {len(names)} model(s) available")
            lines.append(f"model {wanted!r}: {'found' if wanted in names else 'NOT FOUND'}")
    except LlmError as e:
        lines.append(f"NOT reachable: {e}")

    return lines
