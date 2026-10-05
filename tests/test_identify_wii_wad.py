from pathlib import Path

from sort_sys_alpha.identify import build_evidence

# Matches the real header of a Virtual Console WAD dump: 0x00000020 header
# size, then the "Is" type tag.
WAD_HEADER = bytes.fromhex("00000020") + b"Is" + b"\x00" * 24


def test_wii_wad_is_recognized_by_header(tmp_path: Path) -> None:
    path = tmp_path / "Final Fantasy III (Virtual Console).wad"
    path.write_bytes(WAD_HEADER)

    evidence = build_evidence(path)
    assert evidence.kind == "wii_wad"
    assert evidence.details["wad_type"] == "Is"


def test_unrelated_dot_wad_file_is_not_claimed(tmp_path: Path) -> None:
    path = tmp_path / "DOOM.wad"
    path.write_bytes(b"IWAD" + b"\x00" * 28)  # Doom engine WAD, different format entirely

    evidence = build_evidence(path)
    assert evidence.kind != "wii_wad"
