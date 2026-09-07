import numpy as np

from terrain.biomes import make_biomes, subtype_id
from terrain.circle import make_circle
from terrain.config import BiomesConfig, CircleConfig, LandmassConfig
from terrain.debug import StepRecorder
from terrain.landmass import make_landmasses

SIZE = 253


def _world(seed=42):
    rec = StepRecorder(None, False)
    circle = make_circle(SIZE, CircleConfig(), rec)
    land = make_landmasses(circle, LandmassConfig(), seed, rec)
    cfg = BiomesConfig()
    return land, cfg, make_biomes(land, cfg, seed, rec)


def test_subtype_id_formula():
    assert subtype_id(0, 0) == 1
    assert subtype_id(0, 2) == 3
    assert subtype_id(4, 2) == 15


def test_every_biome_on_every_landmass():
    land, cfg, res = _world()
    for lm in (1, 2, 3):
        present = set(np.unique(res.biome_ids[land.landmass_ids == lm]).tolist())
        assert present == {1, 2, 3, 4, 5}


def test_every_subtype_appears():
    _, _, res = _world()
    assert set(np.unique(res.subtype_ids).tolist()) == set(range(16))


def test_region_ids_zero_exactly_on_sea():
    land, _, res = _world()
    assert np.array_equal(res.region_ids == 0, ~land.land_mask)
    assert np.array_equal(res.biome_ids == 0, ~land.land_mask)


def test_coast_regions_touch_coast_band():
    _, cfg, res = _world()
    coast_types = {i for i, t in enumerate(cfg.types) if t.placement == "coast"}
    for r in res.regions:
        if r.biome_index in coast_types:
            pix = res.region_ids == r.id
            assert res.coast_distance[pix].min() <= cfg.coast_band_px


def test_regions_stay_on_their_landmass():
    land, _, res = _world()
    for r in res.regions:
        pix = res.region_ids == r.id
        assert pix.any()
        assert set(np.unique(land.landmass_ids[pix]).tolist()) == {r.landmass_id}


def test_type_names_follow_config_order():
    _, cfg, res = _world()
    assert res.type_names == [t.name for t in cfg.types]


def test_deterministic():
    _, _, a = _world(3)
    _, _, b = _world(3)
    assert np.array_equal(a.subtype_ids, b.subtype_ids)
