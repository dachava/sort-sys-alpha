from pathlib import Path

from sort_sys_alpha.identify import build_evidence


def test_ips_patch_is_recognized_by_magic(tmp_path: Path) -> None:
    path = tmp_path / "translation.ips"
    path.write_bytes(b"PATCH" + b"\x00" * 20 + b"EOF")

    evidence = build_evidence(path)
    assert evidence.kind == "rom_patch"
    assert evidence.details == {"format": "ips"}


def test_dot_ips_without_the_magic_is_not_claimed(tmp_path: Path) -> None:
    path = tmp_path / "notes.ips"
    path.write_text("just some text, not a real patch")

    evidence = build_evidence(path)
    assert evidence.kind != "rom_patch"
