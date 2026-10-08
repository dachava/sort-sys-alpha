from pathlib import Path

from sort_sys_alpha.dat import (
    lookup_title,
    lookup_title_by_crc,
    normalize_serial,
    parse_crc_dat,
    parse_dat,
)

SAMPLE_DAT = """\
clrmamepro (
    name "Sony - PlayStation 2"
    description "Sony - PlayStation 2"
    version "2020.3.19"
    homepage "https://github.com/robloach/libretro-database-psxdatacenter#readme"
)

game (
    name ".Hack - Infection (USA)"
    serial "SLUS-20267"
    description "First in a four-part series."
    developer "CyberConnect2"
    publisher "Bandai"
    releaseyear "2003"
    rom (
        serial "SLUS-20267"
        name ".Hack - Infection (USA).cue"
    )
)

game (
    name "007 - Agent under fire (USA)"
    serial "SLUS-20265"
    description "The western world's favorite super spy is back."
    developer "EA Redwood Shores"
    publisher "Electronic Arts"
    releaseyear "2001"
    rom (
        serial "SLUS-20265"
        name "007 - Agent under fire (USA).cue"
    )
)
"""


def test_normalize_serial_from_dat_style() -> None:
    assert normalize_serial("SLUS-20267") == "SLUS-20267"


def test_normalize_serial_from_system_cnf_style() -> None:
    assert normalize_serial("BOOT2 = CDROM0:\\SLUS_202.67;1") == "SLUS-20267"


def test_normalize_serial_no_match() -> None:
    assert normalize_serial("VER = 1.00") is None


def test_parse_dat_extracts_outer_name_and_serial_not_the_nested_rom() -> None:
    titles = parse_dat(SAMPLE_DAT)
    assert titles == {
        "SLUS-20267": ".Hack - Infection (USA)",
        "SLUS-20265": "007 - Agent under fire (USA)",
    }


def test_lookup_title_matches_normalized_serial(tmp_path: Path) -> None:
    dat_path = tmp_path / "ps2.dat"
    dat_path.write_text(SAMPLE_DAT)

    title = lookup_title("ps2", "CDROM0:\\SLUS_202.67;1", {"ps2": dat_path})
    assert title == ".Hack - Infection (USA)"


def test_lookup_title_no_console_configured(tmp_path: Path) -> None:
    dat_path = tmp_path / "ps2.dat"
    dat_path.write_text(SAMPLE_DAT)

    assert lookup_title("psx", "SLUS-20267", {"ps2": dat_path}) is None


def test_lookup_title_unknown_serial(tmp_path: Path) -> None:
    dat_path = tmp_path / "ps2.dat"
    dat_path.write_text(SAMPLE_DAT)

    assert lookup_title("ps2", "SLUS-99999", {"ps2": dat_path}) is None


SAMPLE_CRC_DAT = """\
clrmamepro (
	name "Nintendo - Super Nintendo Entertainment System"
	description "Nintendo - Super Nintendo Entertainment System"
)

game (
	comment "3 Ninjas Kick Back (USA)"
	developer "Malibu Games"
	rom ( crc F2EE11F9 )
)

game (
	comment "3-jigen Kakutou Ballz (Japan)"
	developer "Accolade"
	rom ( crc F0810694 )
)
"""


def test_parse_crc_dat_extracts_comment_as_title() -> None:
    titles = parse_crc_dat(SAMPLE_CRC_DAT)
    assert titles == {
        "F2EE11F9": "3 Ninjas Kick Back (USA)",
        "F0810694": "3-jigen Kakutou Ballz (Japan)",
    }


def test_lookup_title_by_crc_matches_case_insensitively(tmp_path: Path) -> None:
    dat_path = tmp_path / "snes.dat"
    dat_path.write_text(SAMPLE_CRC_DAT)

    title = lookup_title_by_crc("snes", "f2ee11f9", {"snes": dat_path})
    assert title == "3 Ninjas Kick Back (USA)"


def test_lookup_title_by_crc_no_console_configured(tmp_path: Path) -> None:
    dat_path = tmp_path / "snes.dat"
    dat_path.write_text(SAMPLE_CRC_DAT)

    assert lookup_title_by_crc("nes", "F2EE11F9", {"snes": dat_path}) is None


def test_lookup_title_by_crc_unknown_crc(tmp_path: Path) -> None:
    dat_path = tmp_path / "snes.dat"
    dat_path.write_text(SAMPLE_CRC_DAT)

    assert lookup_title_by_crc("snes", "DEADBEEF", {"snes": dat_path}) is None
