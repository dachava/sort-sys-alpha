from pathlib import Path

from sort_sys_alpha.identify.download_source import parse_zone_identifier_text, read_zone_identifier


def test_parses_host_and_referrer() -> None:
    text = (
        "[ZoneTransfer]\n"
        "ZoneId=3\n"
        "ReferrerUrl=https://example.com/downloads\n"
        "HostUrl=https://cdn.example.com/file.zip\n"
    )
    result = parse_zone_identifier_text(text)
    assert result == {"source_host": "cdn.example.com", "referrer_host": "example.com"}


def test_missing_fields_are_none() -> None:
    assert parse_zone_identifier_text("[ZoneTransfer]\nZoneId=3\n") == {
        "source_host": None,
        "referrer_host": None,
    }


def test_no_ads_on_this_platform_is_a_no_op(tmp_path: Path) -> None:
    path = tmp_path / "file.zip"
    path.write_bytes(b"\x00")

    assert read_zone_identifier(path) == {"source_host": None, "referrer_host": None}
