import numpy as np

from terrain.biomes import make_biomes
from terrain.circle import make_circle
from terrain.config import BiomesConfig, CircleConfig, HeightmapConfig, LandmassConfig, Profile
from terrain.debug import StepRecorder
from terrain.heightmap import biome_weights, make_heightmap
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
    lowest = min(0.0, min(p.base for p in cfg.profiles.values()))
    assert h[land.land_mask].min() >= lowest - 1e-6 and h[land.land_mask].max() <= 1.0
    sea = h[~land.land_mask]
    assert sea.max() <= 0.0 and sea.min() >= -cfg.seabed_depth - 1e-6


def test_coast_is_near_zero_and_outside_is_floor():
    circle, land, biomes, cfg, res = _world()
    coast = land.land_mask & (biomes.coast_distance <= 1.5)
    assert res.height[coast].max() < 0.02
    assert np.allclose(res.height[~circle.mask], -cfg.seabed_depth)


def _inland_mean(res, biomes, cfg, name):
    index = biomes.type_names.index(name) + 1
    sel = (biomes.coast_distance > cfg.coast_distance_px) & (biomes.biome_ids == index)
    assert sel.sum() > 50
    return float(res.height[sel].mean())


def _small_world_cfg(blend_px=5.0):
    """Regions at size 253 are small, so the tests use a short coast rise and a narrow blend."""
    cfg = HeightmapConfig(coast_distance_px=15.0, coast_blur_px=3.0)
    for p in cfg.profiles.values():
        p.blend_px = blend_px
    return cfg


def test_each_biome_uses_its_own_profile():
    circle, land, biomes, cfg, res = _world(cfg=_small_world_cfg())
    assert _inland_mean(res, biomes, cfg, "mountain_range") > _inland_mean(res, biomes, cfg, "marshlands") + 0.2


def test_biome_weights_sum_to_one_where_a_biome_is_near():
    ids = np.zeros((32, 32), dtype=np.int32)
    ids[4:28, 4:16] = 1
    ids[4:28, 16:28] = 2
    w = biome_weights(ids, [3.0, 8.0])
    assert w.shape == (2, 32, 32)
    assert np.allclose(w.sum(0)[ids > 0], 1.0)


def test_higher_base_gives_higher_land():
    def profiles(base):
        return {name: Profile(base, 0.1, 6.0, 4) for name in HeightmapConfig().profiles}
    _, land, _, _, low = _world(cfg=HeightmapConfig(profiles=profiles(0.2)))
    _, _, _, _, high = _world(cfg=HeightmapConfig(profiles=profiles(0.6)))
    assert high.height[land.land_mask].mean() > low.height[land.land_mask].mean()


def test_wider_blend_smooths_the_border():
    def cfg_with(blend_px):
        cfg = _small_world_cfg(blend_px)
        for name, p in cfg.profiles.items():
            cfg.profiles[name] = Profile(0.9 if name == "mountain_range" else 0.1, 0.0, 6.0, 1, blend_px=blend_px)
        return cfg

    def max_inland_slope(cfg):
        _, land, biomes, _, res = _world(cfg=cfg)
        gy, gx = np.gradient(res.height)
        inland = biomes.coast_distance > 2 * cfg.coast_distance_px
        return float(np.hypot(gy, gx)[inland].max())

    assert max_inland_slope(cfg_with(30.0)) < max_inland_slope(cfg_with(2.0))


def test_negative_base_puts_land_below_sea_level():
    def cfg_with(base):
        cfg = _small_world_cfg()
        for name in cfg.profiles:
            cfg.profiles[name] = Profile(base, 0.0, 6.0, 1, blend_px=5.0)
        return cfg
    _, land, biomes, cfg, flat = _world(cfg=cfg_with(0.0))
    _, _, _, _, sunk = _world(cfg=cfg_with(-0.1))
    inland = biomes.coast_distance > 2 * cfg.coast_distance_px
    assert flat.height[inland].min() >= 0.0
    assert np.isclose(sunk.height[inland].min(), -0.1, atol=1e-6)


def test_noise_only_adds_height_above_the_base():
    cfg = _small_world_cfg()
    for name in cfg.profiles:
        cfg.profiles[name] = Profile(0.2, 0.5, 6.0, 4, blend_px=5.0)
    _, land, biomes, cfg, res = _world(cfg=cfg)
    inland = biomes.coast_distance > 2 * cfg.coast_distance_px
    assert res.height[inland].min() >= 0.2 - 1e-6
    assert res.height[inland].max() > 0.3


def test_spit_rises_to_its_profile_base_within_the_spit_rise_distance():
    from terrain.config import SpitConfig
    rec = StepRecorder(None, False)
    circle = make_circle(SIZE, CircleConfig(), rec)
    land = make_landmasses(circle, LandmassConfig(), 42, rec, SpitConfig())
    biomes = make_biomes(land, BiomesConfig(), 42, rec)
    cfg = HeightmapConfig()
    cfg.profiles["sea_side"] = Profile(0.05, 0.1, 12.0, 3, blend_px=2.0)
    res = make_heightmap(circle, land, biomes, cfg, 42, rec, spit_rise_px=2.0)
    inner = land.spit_mask & (biomes.coast_distance >= 2.0)
    assert inner.sum() > 20
    assert res.height[inner].min() >= 0.05 - 0.01
    edge = land.spit_mask & (biomes.coast_distance <= 1.0)
    assert res.height[edge].max() <= 0.5 * (0.05 + 0.1) + 1e-6
    assert res.height[edge].mean() < res.height[inner].mean()
