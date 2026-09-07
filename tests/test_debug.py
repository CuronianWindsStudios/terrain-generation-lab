import numpy as np

from terrain.debug import StepRecorder
from terrain.imageio import load_array, save_gray16, to_uint8


def test_to_uint8_bool_and_float():
    assert to_uint8(np.array([[True, False]])).tolist() == [[255, 0]]
    out = to_uint8(np.array([[0.0, 0.5, 1.0]], dtype=np.float32))
    assert out.tolist() == [[0, 128, 255]]
    flat = to_uint8(np.zeros((2, 2), dtype=np.float32))
    assert flat.max() == 0


def test_save_gray16_round_trip(tmp_path):
    arr = np.array([[0, 32768], [65535, 1]], dtype=np.uint16)
    path = tmp_path / "h.png"
    save_gray16(path, arr)
    back = load_array(path)
    assert back.dtype == np.uint16
    assert np.array_equal(back, arr)


def test_recorder_disabled_writes_nothing(tmp_path):
    rec = StepRecorder(tmp_path, enabled=False)
    rec.step("01a", "Center distance", np.zeros((4, 4)), "text")
    assert rec.write_walkthrough() is None
    assert not (tmp_path / "steps").exists()


def test_recorder_writes_image_and_walkthrough(tmp_path):
    rec = StepRecorder(tmp_path, enabled=True)
    rec.step("01a", "Center distance", np.zeros((4, 4)), "The distance from the center.", {"size": 4})
    rec.note("02-retry-0", "Retry", "Try 1 gave 2 landmasses.", {"count": 2})
    path = rec.write_walkthrough()
    assert (tmp_path / "steps" / "01a_center_distance.png").exists()
    text = path.read_text(encoding="utf-8")
    assert "## Step 01a: Center distance" in text
    assert "| size | 4 |" in text
    assert "![Step 01a](steps/01a_center_distance.png)" in text
    assert "## Step 02-retry-0: Retry" in text
