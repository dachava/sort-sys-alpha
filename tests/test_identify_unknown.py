from pathlib import Path

from sort_sys_alpha.identify import build_evidence


def test_unrecognized_binary_falls_back_to_unknown(tmp_path: Path) -> None:
    path = tmp_path / "mystery.xyz123"
    path.write_bytes(b"\x01\x02\x03AB\xff\x00")

    evidence = build_evidence(path)
    assert evidence.kind == "unknown"
    assert evidence.details["hex_preview"].startswith("010203")
    assert "AB" in evidence.details["printable_preview"]
