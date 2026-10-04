from pathlib import Path

from fixtures.make import make_docx, make_pptx, make_xlsx

from sort_sys_alpha.identify import build_evidence


def test_docx_title_and_preview(tmp_path: Path) -> None:
    path = tmp_path / "report.docx"
    make_docx(path, title="Quarterly Report", text="Revenue is up this quarter.")

    evidence = build_evidence(path)
    assert evidence.kind == "office"
    assert evidence.details["title"] == "Quarterly Report"
    assert "Revenue" in evidence.details["text_preview"]


def test_xlsx_sheet_names(tmp_path: Path) -> None:
    path = tmp_path / "budget.xlsx"
    make_xlsx(path, sheet_names=["Summary", "Q1", "Q2"])

    evidence = build_evidence(path)
    assert evidence.kind == "office"
    assert evidence.details["sheet_names"] == ["Summary", "Q1", "Q2"]


def test_pptx_slide_titles(tmp_path: Path) -> None:
    path = tmp_path / "deck.pptx"
    make_pptx(path, title="Kickoff")

    evidence = build_evidence(path)
    assert evidence.kind == "office"
    assert evidence.details["slide_titles"] == ["Kickoff"]
