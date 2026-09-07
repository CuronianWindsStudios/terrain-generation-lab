import numpy as np

from terrain.biomes import make_biomes
from terrain.circle import make_circle
from terrain.config import BiomesConfig, CircleConfig, HeightmapConfig, LandmassConfig
from terrain.debug import StepRecorder
from terrain.heightmap import biome_weights, make_heightmap
from terrain.landmass import make_landmasses

SIZE = 253


def _world(seed=42):
    rec = StepRecorder(None, False)
    circle = make_circle(SIZE, CircleConfig(), rec)
    land = make_landmasses(circle, LandmassConfig(), seed, rec)
    biomes = make_biomes(land, BiomesConfig(), seed, rec)
    cfg = HeightmapConfig()
    return circle, land, biomes, cfg, make_heightmap(circle, land, biomes, cfg, seed, rec)


def test_ranges():
    circle, land, biomes, cfg, res = _world()
    h = res.height
    assert h.dtype == np.float32
    assert h[land.land_mask].min() >= 0.0 and h[land.land_mask].max() <= 1.0
    sea = h[~land.land_mask]
    assert sea.max() <= 0.0 and sea.min() >= -cfg.seabed_depth - 1e-6


def test_coast_is_near_zero_and_outside_is_floor():
    circle, land, biomes, cfg, res = _world()
    coast = land.land_mask & (biomes.coast_distance <= 1.5)
    assert res.height[coast].max() < 0.02
    assert np.allclose(res.height[~circle.mask], -cfg.seabed_depth)


def test_mountains_higher_than_marsh():
    circle, land, biomes, cfg, res = _world()
    mountain = res.height[biomes.biome_ids == 5].mean()
    marsh = res.height[biomes.biome_ids == 2].mean()
    assert mountain > marsh


def test_biome_weights_sum_to_one_on_land():
    ids = np.zeros((32, 32), dtype=np.int32)
    ids[4:28, 4:16] = 1
    ids[4:28, 16:28] = 2
    w = biome_weights(ids, 2, 3.0)
    assert w.shape == (2, 32, 32)
    assert np.allclose(w.sum(0)[ids > 0], 1.0)
