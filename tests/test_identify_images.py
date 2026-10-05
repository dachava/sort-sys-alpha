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


def test_psd_is_claimed_as_an_image(tmp_path: Path) -> None:
    # Pillow's PSD plugin is read-only, so there's no library helper to
    # build a real one here -- same situation as the truncated-zip test in
    # test_identify_archives.py: dispatch (can_handle) is extension-based,
    # so a file Pillow can't actually decode still gets claimed as "image"
    # and just comes back with no details, rather than falling through to
    # the LLM tier as "unknown".
    path = tmp_path / "artwork.psd"
    path.write_bytes(b"\x00" * 50)

    evidence = build_evidence(path)
    assert evidence.kind == "image"
    assert evidence.details == {}
