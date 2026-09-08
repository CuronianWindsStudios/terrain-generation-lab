import numpy as np
from scipy import ndimage

from terrain.circle import make_circle
from terrain.config import CircleConfig, LandmassConfig, SpitConfig
from terrain.debug import StepRecorder
from terrain.landmass import make_landmasses
from terrain.spit import closing, make_spits

SIZE = 253
EIGHT = np.ones((3, 3), dtype=bool)


def _world(seed=42, **kw):
    rec = StepRecorder(None, False)
    circle = make_circle(SIZE, CircleConfig(), rec)
    land = make_landmasses(circle, LandmassConfig(), seed, rec)
    cfg = SpitConfig(**kw)
    rng = np.random.default_rng(seed)
    return circle, land, cfg, make_spits(circle, land, cfg, rng, rec)


def _contacts(land, res, lm):
    """The number of coast pieces that the bar of landmass lm touches."""
    bar = res.mask & (res.owner == lm)
    touch = ndimage.binary_dilation(bar, structure=EIGHT, iterations=2) & (land.landmass_ids == lm)
    _, n = ndimage.label(touch, structure=EIGHT)
    return n


def test_closing_fills_a_bay():
    m = np.zeros((60, 60), dtype=bool)
    m[10:50, 10:50] = True
    m[25:35, 30:60] = False  # a bay open to the right
    c = closing(m, 12.0)
    assert c[30, 45]  # the bay is filled
    assert c[m].all()  # the land stays
    assert not c[5, 5]  # the open sea stays


def test_one_bar_joined_to_each_landmass():
    circle, land, cfg, res = _world()
    assert res.problem is None
    assert res.mask.dtype == bool
    assert sorted(np.unique(res.owner[res.mask]).tolist()) == [1, 2, 3]
    joined, n = ndimage.label(land.land_mask | res.mask)
    assert n == 3
    for lm in (1, 2, 3):
        bar_labels = set(np.unique(joined[res.mask & (res.owner == lm)]).tolist())
        land_labels = set(np.unique(joined[land.landmass_ids == lm]).tolist())
        assert bar_labels == land_labels


def test_bars_keep_a_gap_from_other_land():
    circle, land, cfg, res = _world()
    for lm in (1, 2, 3):
        other = (land.landmass_ids > 0) & (land.landmass_ids != lm)
        other |= res.mask & (res.owner != lm)
        dist = ndimage.distance_transform_edt(~other)
        assert dist[res.mask & (res.owner == lm)].min() >= cfg.gap_pct / 100.0 * circle.radius * 0.5


def test_water_lies_behind_the_middle_of_the_bar():
    circle, land, cfg, res = _world()
    dist = ndimage.distance_transform_edt(~land.land_mask)
    clearance = cfg.lagoon_pct / 100.0 * circle.radius
    for lm in (1, 2, 3):
        path = res.paths[lm - 1]
        middle = path[len(path) // 3: 2 * len(path) // 3]
        d = dist[np.round(middle[:, 1]).astype(int), np.round(middle[:, 0]).astype(int)]
        assert d.min() >= 0.5 * clearance


def test_bar_without_strait_encloses_a_lagoon():
    circle, land, cfg, res = _world(strait_pct=0.0)
    sea = ~(land.land_mask | res.mask)
    labels, n = ndimage.label(sea)
    open_sea = labels[0, 0]
    for lm in (1, 2, 3):
        assert _contacts(land, res, lm) >= 2
        bar = res.mask & (res.owner == lm)
        beside = ndimage.binary_dilation(bar, structure=EIGHT, iterations=2) & sea
        enclosed = {int(v) for v in np.unique(labels[beside]) if v not in (0, open_sea)}
        assert enclosed
        area = sum(int((labels == v).sum()) for v in enclosed)
        assert area >= 0.5 * cfg.min_lagoon_pct / 100.0 * (land.landmass_ids == lm).sum()


def test_bar_with_strait_joins_one_side_only():
    circle, land, cfg, res = _world()
    assert cfg.strait_pct > 0
    for lm in (1, 2, 3):
        assert _contacts(land, res, lm) == 1


def test_bar_is_long_and_thin():
    circle, land, cfg, res = _world()
    width = cfg.width_pct / 100.0 * circle.radius
    for lm in (1, 2, 3):
        bar = res.mask & (res.owner == lm)
        length = res.lengths_px[lm - 1]
        assert length >= 0.6 * cfg.length_pct[0] / 100.0 * circle.radius
        assert bar.sum() / length <= width * (1.0 + cfg.width_variation) * 2.0


def test_bars_stay_inside_the_circle():
    circle, land, cfg, res = _world()
    assert not (res.mask & ~circle.mask).any()


def test_deterministic():
    _, _, _, a = _world(7)
    _, _, _, b = _world(7)
    assert np.array_equal(a.mask, b.mask)


def test_impossible_bar_reports_a_problem():
    circle, land, cfg, res = _world(gap_pct=150)
    assert res.problem is not None
