from pathlib import Path

from fixtures.make import make_torrent

from sort_sys_alpha.identify import build_evidence
from sort_sys_alpha.identify.torrents import decode_torrent


def test_torrent_name(tmp_path: Path) -> None:
    path = tmp_path / "linux.torrent"
    make_torrent(path, name="ubuntu-24.04.iso", length=5_000_000_000)

    evidence = build_evidence(path)
    assert evidence.kind == "torrent"
    assert evidence.details["name"] == "ubuntu-24.04.iso"


def test_torrent_with_file_list() -> None:
    data = (
        b"d4:infod5:filesld6:lengthi1e4:pathl5:a.txteed6:lengthi2e4:pathl5:b.txteee"
        b"4:name4:pack12:piece lengthi16384eee"
    )
    torrent = decode_torrent(data)
    assert torrent[b"info"][b"name"] == b"pack"
    assert len(torrent[b"info"][b"files"]) == 2
