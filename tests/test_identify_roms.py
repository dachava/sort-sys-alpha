from pathlib import Path

from sort_sys_alpha.identify import build_evidence


def test_nes_header(tmp_path: Path) -> None:
    path = tmp_path / "game.nes"
    path.write_bytes(b"NES\x1a" + b"\x00" * 100)

    evidence = build_evidence(path)
    assert evidence.kind == "rom"
    assert evidence.details == {"console": "nes", "verified": True}


def test_gba_header(tmp_path: Path) -> None:
    path = tmp_path / "game.gba"
    data = bytearray(200)
    data[0x04:0x08] = b"\x24\xff\xae\x51"
    path.write_bytes(bytes(data))

    evidence = build_evidence(path)
    assert evidence.details == {"console": "gba", "verified": True}


def test_n64_byte_order_variants(tmp_path: Path) -> None:
    variants = [
        ("a.z64", b"\x80\x37\x12\x40"),
        ("b.v64", b"\x37\x80\x40\x12"),
        ("c.n64", b"\x40\x12\x37\x80"),
    ]
    for name, magic in variants:
        path = tmp_path / name
        path.write_bytes(magic + b"\x00" * 100)
        evidence = build_evidence(path)
        assert evidence.details == {"console": "n64", "verified": True}, name


def test_genesis_header(tmp_path: Path) -> None:
    path = tmp_path / "game.md"
    data = bytearray(600)
    data[0x100:0x104] = b"SEGA"
    path.write_bytes(bytes(data))

    evidence = build_evidence(path)
    assert evidence.details == {"console": "genesis", "verified": True}


def test_gb_vs_gbc_via_cgb_flag(tmp_path: Path) -> None:
    gb = bytearray(400)
    gb[0x104:0x108] = b"\xce\xed\x66\x66"
    gb[0x143] = 0x00
    (tmp_path / "plain.gb").write_bytes(bytes(gb))
    evidence = build_evidence(tmp_path / "plain.gb")
    assert evidence.details["console"] == "gb"

    gbc = bytearray(400)
    gbc[0x104:0x108] = b"\xce\xed\x66\x66"
    gbc[0x143] = 0xC0
    (tmp_path / "color.gbc").write_bytes(bytes(gbc))
    evidence = build_evidence(tmp_path / "color.gbc")
    assert evidence.details["console"] == "gbc"


def test_mislabeled_extension_is_unverified(tmp_path: Path) -> None:
    path = tmp_path / "not_actually_a_rom.nes"
    path.write_bytes(b"\x00" * 100)

    evidence = build_evidence(path)
    assert evidence.details["verified"] is False


def test_snes_and_nds_are_extension_only(tmp_path: Path) -> None:
    (tmp_path / "game.sfc").write_bytes(b"\x00" * 100)
    (tmp_path / "game.nds").write_bytes(b"\x00" * 100)

    sfc = build_evidence(tmp_path / "game.sfc")
    nds = build_evidence(tmp_path / "game.nds")
    assert sfc.details == {"console": "snes", "verified": False}
    assert nds.details == {"console": "nds", "verified": False}
