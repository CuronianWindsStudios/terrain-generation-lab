import numpy as np

from terrain.biomes import make_biomes, subtype_id
from terrain.circle import make_circle
from terrain.config import SUBTYPE_LETTERS, BiomesConfig, CircleConfig, LandmassConfig, SpitConfig
from terrain.debug import StepRecorder
from terrain.landmass import make_landmasses

SIZE = 253


def _world(seed=42):
    rec = StepRecorder(None, False)
    circle = make_circle(SIZE, CircleConfig(), rec)
    land = make_landmasses(circle, LandmassConfig(), seed, rec, SpitConfig())
    cfg = BiomesConfig()
    return land, cfg, make_biomes(land, cfg, seed, rec)


SPIT_BIOME = 1  # sea_side is the first type, biome id 1


def test_sea_side_covers_exactly_the_spits():
    land, cfg, res = _world()
    assert cfg.types[0].placement == "spit"
    assert np.array_equal(res.biome_ids == SPIT_BIOME, land.spit_mask)


def test_each_spit_is_one_region_with_one_sub_type():
    land, _, res = _world()
    for lm in (1, 2, 3):
        spit = land.spit_mask & (land.spit_owner == lm)
        assert len(np.unique(res.region_ids[spit])) == 1
        assert len(np.unique(res.subtype_ids[spit])) == 1


def test_spit_regions_are_listed_once_per_landmass():
    land, cfg, res = _world()
    spit_regions = [r for r in res.regions if r.biome_index == 0]
    assert sorted(r.landmass_id for r in spit_regions) == [1, 2, 3]


def test_each_landmass_has_one_sub_type_per_biome_and_no_two_landmasses_share_it():
    land, cfg, res = _world()
    for t in range(len(cfg.types)):
        letters = []
        for lm in (1, 2, 3):
            regions = [r for r in res.regions if r.biome_index == t and r.landmass_id == lm]
            assert regions
            present = {r.subtype_index for r in regions}
            assert len(present) == 1
            letters.append(present.pop())
        assert sorted(letters) == [0, 1, 2]


def test_sub_type_permutations_differ_between_biomes_for_some_seed():
    # the permutation is random per biome type, so not every biome uses the same A, B, C order
    found = False
    for seed in range(1, 6):
        _, cfg, res = _world(seed)
        orders = set()
        for t in range(len(cfg.types)):
            orders.add(tuple(next(r.subtype_index for r in res.regions
                                  if r.biome_index == t and r.landmass_id == lm) for lm in (1, 2, 3)))
        if len(orders) > 1:
            found = True
            break
    assert found


def test_mainland_regions_do_not_use_spit_pixels():
    land, _, res = _world()
    mainland = land.land_mask & ~land.spit_mask
    assert set(np.unique(res.biome_ids[mainland]).tolist()) == {2, 3, 4, 5}


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
