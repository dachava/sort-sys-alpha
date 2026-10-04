from pathlib import Path

from fixtures.make import make_tar_gz, make_zip

from sort_sys_alpha.identify import build_evidence


def test_zip_lists_members(tmp_path: Path) -> None:
    path = tmp_path / "sample.zip"
    make_zip(path, {"readme.txt": b"hi", "data/one.bin": b"\x00" * 10})

    evidence = build_evidence(path)
    assert evidence.kind == "archive"
    assert evidence.details["member_count"] == 2
    assert "readme.txt" in evidence.details["members"]
    assert evidence.details["uncompressed_size"] == 12


def test_tar_gz_lists_members(tmp_path: Path) -> None:
    path = tmp_path / "sample.tar.gz"
    make_tar_gz(path, {"a.txt": b"hello tar"})

    evidence = build_evidence(path)
    assert evidence.kind == "archive"
    assert evidence.details["members"] == ["a.txt"]


def test_truncated_zip_is_held_gracefully(tmp_path: Path) -> None:
    path = tmp_path / "broken.zip"
    path.write_bytes(b"PK\x03\x04not a real zip")

    evidence = build_evidence(path)
    assert evidence.kind == "archive"
    assert evidence.details == {}
