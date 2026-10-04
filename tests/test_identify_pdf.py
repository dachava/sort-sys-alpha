from pathlib import Path

from fixtures.make import make_pdf

from sort_sys_alpha.identify import build_evidence


def test_pdf_text_and_page_count(tmp_path: Path) -> None:
    path = tmp_path / "statement.pdf"
    make_pdf(path, text="Chase Statement Period Aug 2026")

    evidence = build_evidence(path)
    assert evidence.kind == "pdf"
    assert evidence.details["page_count"] == 1
    assert "Chase Statement" in evidence.details["text_preview"]
    assert evidence.details["is_scanned"] is False


def test_unreadable_pdf_bytes_are_held_gracefully(tmp_path: Path) -> None:
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.4\nnot a real pdf")

    evidence = build_evidence(path)
    assert evidence.kind == "pdf"
    assert evidence.details == {}
