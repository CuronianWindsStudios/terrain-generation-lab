from terrain.config import config_from_dict
from terrain.experiment import build_overrides, generate, save_result


def test_build_overrides_maps_fields():
    o = build_overrides({
        "seed": 5, "size": 253, "diameter": 80.0, "threshold": 0.3, "channel_pct": 20.0,
        "warp_pct": 10.0, "noise_frequency": 4.0, "noise_octaves": 6,
        "radius_min": 90.0, "radius_max": 110.0, "seed_area_pct": 50.0, "min_separation_pct": 70.0,
        "biome_warp_px": 80.0, "seeds_min": 5, "seeds_max": 6, "coast_band_px": 30.0,
        "coast_distance_px": 60.0, "profile_blur_px": 20.0, "seabed_depth": 0.25,
        "profile_mountain_range_base": 0.7, "profile_sea_side_amplitude": 0.02,
    })
    assert o["seed"] == 5 and o["size"] == 253
    assert o["circle"] == {"diameter_pct": 80.0}
    assert o["landmass"]["radius_pct"] == [90.0, 110.0]
    assert o["landmass"]["noise"] == {"frequency": 4.0, "octaves": 6}
    assert o["biomes"]["seeds_per_landmass"] == [5, 6]
    assert o["biomes"]["warp"] == {"strength_px": 80.0}
    assert o["heightmap"]["profiles"] == {"mountain_range": {"base": 0.7}, "sea_side": {"amplitude": 0.02}}
    cfg = config_from_dict(o)
    assert cfg.heightmap.profiles["mountain_range"].base == 0.7
    assert cfg.heightmap.profiles["mountain_range"].ridged is True


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
