from pathlib import Path

from sort_sys_alpha.identify import build_evidence


def test_safetensors_is_recognized_by_header_structure(tmp_path: Path) -> None:
    header_json = b'{"__metadata__":{"format":"pt"}}'
    path = tmp_path / "model.safetensors"
    path.write_bytes(len(header_json).to_bytes(8, "little") + header_json + b"\x00" * 10)

    evidence = build_evidence(path)
    assert evidence.kind == "ml_weights"
    assert evidence.details == {"format": "safetensors"}


def test_garbage_dot_safetensors_is_not_claimed(tmp_path: Path) -> None:
    path = tmp_path / "not_really.safetensors"
    path.write_bytes(b"\xff" * 20)

    evidence = build_evidence(path)
    assert evidence.kind != "ml_weights"
