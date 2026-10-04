from pathlib import Path

from fixtures.make import make_png

from sort_sys_alpha.identify import build_evidence


def test_screen_resolution_with_no_camera_exif_looks_like_a_screenshot(tmp_path: Path) -> None:
    path = tmp_path / "IMG_shot.png"
    make_png(path, size=(1920, 1080), exif={"Software": "Snipping Tool"})

    evidence = build_evidence(path)
    assert evidence.kind == "image"
    assert evidence.details["width"] == 1920
    assert evidence.details["height"] == 1080
    assert evidence.details["looks_like_screenshot"] is True


def test_camera_exif_does_not_look_like_a_screenshot(tmp_path: Path) -> None:
    path = tmp_path / "DSC_0001.jpg"
    make_png(path, size=(1920, 1080), exif={"Make": "TestCo", "Model": "TestCam X"})

    evidence = build_evidence(path)
    assert evidence.details["exif"]["Make"] == "TestCo"
    assert evidence.details["looks_like_screenshot"] is False


def test_filename_says_screenshot_even_without_matching_resolution(tmp_path: Path) -> None:
    path = tmp_path / "Screenshot 2026-01-01.png"
    make_png(path, size=(400, 300))

    evidence = build_evidence(path)
    assert evidence.details["looks_like_screenshot"] is True
