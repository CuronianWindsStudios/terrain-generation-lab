import numpy as np
import pytest
from scipy import ndimage

from terrain.circle import make_circle
from terrain.config import CircleConfig, GenerationError, LandmassConfig
from terrain.debug import StepRecorder
from terrain.landmass import make_landmasses

SIZE = 253


def _land(seed=42, **kw):
    circle = make_circle(SIZE, CircleConfig(), StepRecorder(None, False))
    cfg = LandmassConfig(**kw)
    return circle, make_landmasses(circle, cfg, seed, StepRecorder(None, False))


def test_exactly_three_landmasses():
    circle, res = _land()
    _, n = ndimage.label(res.land_mask)
    assert n == 3
    assert sorted(np.unique(res.landmass_ids).tolist()) == [0, 1, 2, 3]


def test_all_land_inside_circle():
    circle, res = _land()
    assert not (res.land_mask & ~circle.mask).any()


def test_ids_ordered_by_area():
    _, res = _land()
    areas = [int((res.landmass_ids == i).sum()) for i in (1, 2, 3)]
    assert areas == sorted(areas, reverse=True)


def test_no_small_lakes():
    _, res = _land(min_lake_area_px=200)
    sea_labels, n = ndimage.label(~res.land_mask)
    sizes = ndimage.sum(~res.land_mask, sea_labels, range(1, n + 1))
    assert all(s >= 200 for s in sizes)


def test_impossible_config_raises():
    with pytest.raises(GenerationError, match="landmasses after 2 tries"):
        _land(threshold=5.0, max_retries=2)


def test_deterministic():
    _, a = _land(seed=7)
    _, b = _land(seed=7)
    assert np.array_equal(a.landmass_ids, b.landmass_ids)
