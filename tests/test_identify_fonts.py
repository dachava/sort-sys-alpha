from pathlib import Path

from fixtures.make import make_font

from sort_sys_alpha.identify import build_evidence


def test_font_family_and_style(tmp_path: Path) -> None:
    path = tmp_path / "custom.ttf"
    make_font(path, family="Acme Sans", style="Bold")

    evidence = build_evidence(path)
    assert evidence.kind == "font"
    assert evidence.details["family"] == "Acme Sans"
    assert evidence.details["style"] == "Bold"
