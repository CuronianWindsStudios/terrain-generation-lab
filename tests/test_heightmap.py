import numpy as np

from terrain.biomes import make_biomes
from terrain.circle import make_circle
from terrain.config import BiomesConfig, CircleConfig, HeightmapConfig, LandmassConfig, Profile
from terrain.debug import StepRecorder
from terrain.heightmap import make_heightmap
from terrain.landmass import make_landmasses

SIZE = 253


def _world(seed=42, cfg=None):
    rec = StepRecorder(None, False)
    circle = make_circle(SIZE, CircleConfig(), rec)
    land = make_landmasses(circle, LandmassConfig(), seed, rec)
    biomes = make_biomes(land, BiomesConfig(), seed, rec)
    cfg = cfg or HeightmapConfig()
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


def test_all_biomes_share_the_profile():
    circle, land, biomes, cfg, res = _world(cfg=HeightmapConfig(coast_distance_px=15.0, coast_blur_px=3.0))
    inland = biomes.coast_distance > cfg.coast_distance_px
    means = [float(res.height[inland & (biomes.biome_ids == b)].mean()) for b in range(1, 6)
             if (inland & (biomes.biome_ids == b)).sum() > 50]
    assert len(means) >= 3
    assert max(means) - min(means) < 0.15


def test_higher_base_gives_higher_land():
    _, land, _, _, low = _world(cfg=HeightmapConfig(profile=Profile(0.2, 0.1, 6.0, 4)))
    _, _, _, _, high = _world(cfg=HeightmapConfig(profile=Profile(0.6, 0.1, 6.0, 4)))
    assert high.height[land.land_mask].mean() > low.height[land.land_mask].mean()
