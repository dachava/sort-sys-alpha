from pathlib import Path

from fixtures.make import make_wav

from sort_sys_alpha.identify import build_evidence


def test_wav_duration(tmp_path: Path) -> None:
    path = tmp_path / "clip.wav"
    make_wav(path, seconds=2.0)

    evidence = build_evidence(path)
    assert evidence.kind == "audio_video"
    assert evidence.details["duration_s"] == 2.0


def test_video_without_ffprobe_on_path_is_held_gracefully(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _name: None)
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"\x00" * 32)

    evidence = build_evidence(path)
    assert evidence.kind == "audio_video"
    assert evidence.details == {}
