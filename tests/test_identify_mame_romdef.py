from pathlib import Path

from sort_sys_alpha.identify import build_evidence

ROMDEF_CONTENT = """\
#mame set of  ctomaday
game  ctomaday  MVS "Captain Tomaday"
CPU 0x200000
249-p1.bin 0x100000 0x100000 NORM
- 0x0 0x100000 NORM
END
SFIX 0x20000
249-s1.bin 0x0 0x20000 NORM
END
SM1 0x20000
249-m1.bin 0x0 0x20000 NORM
END
SOUND1 0x500000
249-v1.bin 0x0 0x400000 NORM
249-v2.bin 0x400000 0x100000 NORM
END
GFX 0x800000
249-c1.bin 0x0 0x400000 ALTERNATE
249-c2.bin 0x1 0x400000 ALTERNATE
END
END
"""


def test_mame_romdef_is_recognized_by_content(tmp_path: Path) -> None:
    path = tmp_path / "ctomaday.rc"
    path.write_text(ROMDEF_CONTENT)

    evidence = build_evidence(path)
    assert evidence.kind == "mame_romdef"
    assert evidence.details["game_title"] == "Captain Tomaday"


def test_unrelated_dot_rc_file_is_not_claimed(tmp_path: Path) -> None:
    path = tmp_path / "bashrc.rc"
    path.write_text("export PATH=$PATH:/usr/local/bin\nalias ll='ls -la'\n")

    evidence = build_evidence(path)
    assert evidence.kind != "mame_romdef"
