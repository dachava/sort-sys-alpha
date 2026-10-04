import json
from datetime import UTC, datetime
from pathlib import Path

from sort_sys_alpha.config import Config
from sort_sys_alpha.feedback import RoutingEntry
from sort_sys_alpha.identify.types import Evidence
from sort_sys_alpha.llm.prompts import build_system_prompt, build_user_message


def test_system_prompt_lists_the_folder_allowlist() -> None:
    config = Config()
    prompt = build_system_prompt(config)
    assert "Images" in prompt
    assert "Documents/Notes" in prompt


def test_system_prompt_has_no_examples_section_without_history() -> None:
    prompt = build_system_prompt(Config())
    assert "Recent accepted examples" not in prompt


def test_system_prompt_includes_few_shot_examples() -> None:
    example = RoutingEntry(
        run_id="run1",
        timestamp=datetime.now(UTC),
        move_root=Path("mystery.xyz"),
        backend="ollama",
        model="test-model",
        prompt_version="v1",
        evidence={"original_name": "mystery.xyz", "kind": "unknown"},
        category="Documents",
        name="a-mystery-file",
        confidence=0.9,
        reason="looks like a document",
        outcome="moved",
    )
    prompt = build_system_prompt(Config(), [example])
    assert "Recent accepted examples" in prompt
    assert "mystery.xyz" in prompt
    assert "a-mystery-file" in prompt


def test_user_message_is_evidence_as_json() -> None:
    evidence = Evidence(
        path=Path("report.pdf"),
        original_name="report.pdf",
        extension=".pdf",
        size=1234,
        created=datetime.now(UTC),
        modified=datetime.now(UTC),
        kind="pdf",
        details={"title": "Q3 Report"},
    )
    message = build_user_message(evidence)
    data = json.loads(message)
    assert data["original_name"] == "report.pdf"
    assert data["kind"] == "pdf"
    assert data["details"]["title"] == "Q3 Report"
