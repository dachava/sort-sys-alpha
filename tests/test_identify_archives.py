from pathlib import Path

from fixtures.make import make_7z, make_tar_gz, make_zip

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


def test_rar_is_classified_as_an_archive_without_listing_members(tmp_path: Path) -> None:
    path = tmp_path / "sample.rar"
    path.write_bytes(b"Rar!\x1a\x07\x01\x00" + b"\x00" * 20)

    evidence = build_evidence(path)
    assert evidence.kind == "archive"
    assert evidence.details == {}


def test_7z_lists_members(tmp_path: Path) -> None:
    path = tmp_path / "sample.7z"
    make_7z(path, {"readme.txt": b"hi", "game.sfc": b"\x00" * 10})

    evidence = build_evidence(path)
    assert evidence.kind == "archive"
    assert evidence.details["member_count"] == 2
    assert "readme.txt" in evidence.details["members"]
    assert "game.sfc" in evidence.details["members"]
    assert evidence.details["uncompressed_size"] == 12


def test_truncated_7z_is_held_gracefully(tmp_path: Path) -> None:
    path = tmp_path / "broken.7z"
    path.write_bytes(b"7z\xbc\xaf\x27\x1c" + b"\x00" * 20)

    evidence = build_evidence(path)
    assert evidence.kind == "archive"
    assert evidence.details == {}
