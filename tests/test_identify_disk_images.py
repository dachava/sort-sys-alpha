from pathlib import Path

from fixtures.make import make_disc_magic, make_iso9660

from sort_sys_alpha.identify import build_evidence


def test_generic_iso_has_volume_label_and_no_console(tmp_path: Path) -> None:
    path = tmp_path / "ubuntu.iso"
    make_iso9660(path, volume_id="UBUNTU_LIVE")

    evidence = build_evidence(path)
    assert evidence.kind == "disk_image"
    assert evidence.details["volume_label"] == "UBUNTU_LIVE"
    assert evidence.details["disc_kind"] == "iso9660"
    assert "console" not in evidence.details


def test_ps2_disc_via_system_cnf_boot2(tmp_path: Path) -> None:
    path = tmp_path / "game.iso"
    system_cnf = b"BOOT2 = cdrom0:\\SCES_123.45;1\r\n"
    make_iso9660(path, volume_id="GAME", root_files={"SYSTEM.CNF": system_cnf})

    evidence = build_evidence(path)
    assert evidence.details["console"] == "ps2"
    assert evidence.details["disc_kind"] == "playstation"


def test_psx_disc_via_system_cnf_boot(tmp_path: Path) -> None:
    path = tmp_path / "game.iso"
    system_cnf = b"BOOT = cdrom:\\SCUS_123.45;1\r\n"
    make_iso9660(path, volume_id="GAME", root_files={"SYSTEM.CNF": system_cnf})

    evidence = build_evidence(path)
    assert evidence.details["console"] == "psx"


def test_psp_disc_via_marker_file(tmp_path: Path) -> None:
    path = tmp_path / "game.iso"
    make_iso9660(path, volume_id="GAME", root_files={"UMD_DATA.BIN": b"data"})

    evidence = build_evidence(path)
    assert evidence.details["console"] == "psp"


def test_gamecube_magic(tmp_path: Path) -> None:
    path = tmp_path / "game.iso"
    make_disc_magic(path, offset=0x1C, magic=b"\xc2\x33\x9f\x3d")

    evidence = build_evidence(path)
    assert evidence.details == {"console": "gc", "disc_kind": "gamecube"}


def test_wii_magic(tmp_path: Path) -> None:
    path = tmp_path / "game.iso"
    make_disc_magic(path, offset=0x18, magic=b"\x5d\x1c\x9e\xa3")

    evidence = build_evidence(path)
    assert evidence.details == {"console": "wii", "disc_kind": "wii"}


def test_not_an_iso_at_all(tmp_path: Path) -> None:
    path = tmp_path / "random.img"
    path.write_bytes(b"\x00" * (3 * 2048))

    evidence = build_evidence(path)
    assert evidence.kind == "disk_image"
    assert evidence.details == {"disc_kind": "unknown"}
