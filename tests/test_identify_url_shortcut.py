from pathlib import Path

from sort_sys_alpha.identify import build_evidence

SHORTCUT = "[InternetShortcut]\nURL=https://example.com/page\n"


def test_url_shortcut_is_recognized_by_content(tmp_path: Path) -> None:
    path = tmp_path / "A saved page.url"
    path.write_text(SHORTCUT)

    evidence = build_evidence(path)
    assert evidence.kind == "url_shortcut"
    assert evidence.details["target_url"] == "https://example.com/page"


def test_unrelated_dot_url_file_is_not_claimed(tmp_path: Path) -> None:
    path = tmp_path / "notes.url"
    path.write_text("not actually a shortcut file")

    evidence = build_evidence(path)
    assert evidence.kind != "url_shortcut"
