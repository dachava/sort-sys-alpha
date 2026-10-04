import json
from datetime import UTC, datetime
from pathlib import Path

from sort_sys_alpha.config import Config
from sort_sys_alpha.identify.types import Evidence
from sort_sys_alpha.llm.prompts import build_system_prompt, build_user_message


def test_system_prompt_lists_the_folder_allowlist() -> None:
    config = Config()
    prompt = build_system_prompt(config)
    assert "Images" in prompt
    assert "Documents/Notes" in prompt


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
