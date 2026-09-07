import numpy as np

from terrain.circle import make_circle
from terrain.config import CircleConfig
from terrain.debug import StepRecorder


def test_mask_width_matches_diameter():
    size = 253
    cfg = CircleConfig(diameter_pct=90.0, edge_band_pct=10.0)
    res = make_circle(size, cfg, StepRecorder(None, False))
    row = res.mask[size // 2]
    width = int(row.sum())
    assert abs(width - size * 0.9) <= 1
    assert res.mask.dtype == np.bool_
    assert res.mask.shape == (size, size)


def test_edge_band_is_one_inside_and_zero_at_edge():
    size = 253
    res = make_circle(size, CircleConfig(diameter_pct=90.0, edge_band_pct=10.0), StepRecorder(None, False))
    c = size // 2
    assert res.edge_band[c, c] == 1.0
    assert res.edge_band[c, 0] == 0.0
    inner = int(res.radius * 0.85)
    assert res.edge_band[c, c + inner] == 1.0
    assert 0.0 < res.edge_band[c, c + int(res.radius * 0.96)] < 1.0


def test_records_three_steps(tmp_path):
    rec = StepRecorder(tmp_path, True)
    make_circle(127, CircleConfig(), rec)
    assert [r.step_id for r in rec.records] == ["01a", "01b", "01c"]
