import numpy as np

from terrain.config import Profile, config_from_dict
from terrain.experiment import build_overrides, generate, profile_height_crop, profile_preview, save_result
from terrain.heightmap import STAGE
from terrain.noise import fractal_noise


def test_build_overrides_maps_fields():
    o = build_overrides({
        "seed": 5, "size": 253, "diameter": 80.0, "threshold": 0.3, "channel_pct": 20.0,
        "warp_pct": 10.0, "noise_frequency": 4.0, "noise_octaves": 6,
        "radius_min": 90.0, "radius_max": 110.0, "seed_area_pct": 50.0, "min_separation_pct": 70.0,
        "biome_warp_px": 80.0, "seeds_min": 5, "seeds_max": 6, "coast_band_px": 30.0,
        "coast_distance_px": 60.0, "seabed_depth": 0.25,
        "profile_mountain_range_base": 0.7, "profile_mountain_range_amplitude": 0.02,
        "profile_mountain_range_noise": "billow", "profile_sea_side_blend_px": 8.0,
        "profile_sea_side_persistence": 0.4,
    })
    assert o["seed"] == 5 and o["size"] == 253
    assert o["circle"] == {"diameter_pct": 80.0}
    assert o["landmass"]["radius_pct"] == [90.0, 110.0]
    assert o["landmass"]["noise"] == {"frequency": 4.0, "octaves": 6}
    assert o["biomes"]["seeds_per_landmass"] == [5, 6]
    assert o["biomes"]["warp"] == {"strength_px": 80.0}
    assert o["heightmap"]["profiles"] == {
        "mountain_range": {"base": 0.7, "amplitude": 0.02, "noise": "billow"},
        "sea_side": {"blend_px": 8.0, "persistence": 0.4},
    }
    cfg = config_from_dict(o)
    assert cfg.heightmap.profiles["mountain_range"].base == 0.7
    assert cfg.heightmap.profiles["mountain_range"].noise == "billow"
    assert cfg.heightmap.profiles["mountain_range"].octaves == 6
    assert cfg.heightmap.profiles["sea_side"].blend_px == 8.0


def test_build_overrides_partial():
    assert build_overrides({"seed": 1}) == {"seed": 1}


def test_generate_and_save(tmp_path):
    res = generate({"size": 127, "seed": 3}, tmp_path / "work")
    assert len(res.steps) >= 30
    assert res.biomes_color.exists() and res.height_shaded.exists() and res.heightmap.exists()
    assert res.seconds > 0
    files = save_result(res, tmp_path / "saved")
    names = {p.name for p in files}
    assert {"config.yaml", "heightmap.png", "biomes_color.png"} <= names
    text = (tmp_path / "saved" / "config.yaml").read_text(encoding="utf-8")
    assert "seed: 3" in text


def test_profile_height_crop_is_the_center_of_the_map_noise():
    profile = Profile(0.4, 0.2, 6.0, 4)
    crop = profile_height_crop(profile, size=253, seed=7, biome_index=2, crop_px=60)
    full = fractal_noise((253, 253), 4, 6.0, 2.0, 0.5, np.random.default_rng([7, STAGE, 2]))
    start = (253 - 60) // 2
    expected = 0.4 + 0.2 * full[start:start + 60, start:start + 60]
    assert crop.shape == (60, 60)
    assert np.allclose(crop, expected, atol=1e-6)


def test_profile_height_crop_clips_to_the_top():
    crop = profile_height_crop(Profile(0.9, 0.5, 6.0, 3), size=127, seed=1, biome_index=0, crop_px=40)
    assert crop.min() >= 0.9 and crop.max() <= 1.0


def test_profile_preview_is_an_8bit_image_that_follows_the_base():
    low = profile_preview(Profile(0.1, 0.05, 6.0, 3), size=127, seed=1, biome_index=0, crop_px=40)
    high = profile_preview(Profile(0.8, 0.05, 6.0, 3), size=127, seed=1, biome_index=0, crop_px=40)
    assert low.dtype == np.uint8 and low.shape == (40, 40, 3)
    assert high.mean() > low.mean()


def test_profile_preview_marks_water_in_blue():
    img = profile_preview(Profile(-0.2, 0.0, 6.0, 3), size=127, seed=1, biome_index=0, crop_px=40)
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    assert (b > r).all() and (b > g).all()
