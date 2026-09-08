import io
import json
import zipfile

import numpy as np

from terrain.config import Profile, config_from_dict
from terrain.experiment import (
    build_overrides,
    export_zip,
    generate,
    profile_height_crop,
    profile_preview,
    save_result,
    settings_json,
)
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


def test_build_overrides_maps_spit_fields():
    o = build_overrides({
        "spit_bay_pct": 12.0, "spit_length_min": 20.0, "spit_length_max": 60.0, "spit_lagoon_pct": 5.0,
        "spit_min_lagoon_pct": 2.0, "spit_width_pct": 4.0,
        "spit_width_variation": 0.4, "spit_strait_pct": 3.0, "spit_gap_pct": 7.0,
        "spit_edge_noise_pct": 1.0, "spit_rise_px": 5.0,
    })
    assert o == {"spit": {"bay_pct": 12.0, "length_pct": [20.0, 60.0], "lagoon_pct": 5.0, "min_lagoon_pct": 2.0,
                          "width_pct": 4.0, "width_variation": 0.4,
                          "strait_pct": 3.0, "gap_pct": 7.0, "edge_noise_pct": 1.0, "rise_px": 5.0}}
    cfg = config_from_dict(o)
    assert cfg.spit.length_pct == (20.0, 60.0) and cfg.spit.strait_pct == 3.0


def test_settings_json_is_the_full_config():
    text = settings_json({"seed": 5, "spit": {"lagoon_pct": 5.0}})
    data = json.loads(text)
    assert data["seed"] == 5 and data["spit"]["lagoon_pct"] == 5.0
    assert data["size"] == 1009 and "profiles" in data["heightmap"]
    assert config_from_dict(data).spit.lagoon_pct == 5.0


def test_export_zip_holds_config_and_unreal_files(tmp_path):
    res = generate({"size": 127, "seed": 3}, tmp_path / "work")
    data = export_zip(res)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        assert {"config.json", "config.yaml", "README.txt"} <= names
        assert "unreal/heightmap.png" in names and "unreal/params.json" in names
        assert sum(n.startswith("unreal/weight_") for n in names) == 5
        assert sum(n.startswith("unreal/subtype_") for n in names) == 15
        assert "preview/biomes_color.png" in names
        cfg = json.loads(zf.read("config.json"))
        assert cfg["seed"] == 3 and cfg["size"] == 127


def test_build_overrides_maps_the_biome_balance_fields():
    o = build_overrides({"balance_iterations": 12, "balance_tolerance": 0.08})
    assert o == {"biomes": {"balance_iterations": 12, "balance_tolerance": 0.08}}


def test_build_overrides_partial():
    assert build_overrides({"seed": 1}) == {"seed": 1}


def test_generate_and_save(tmp_path):
    res = generate({"size": 127, "seed": 3}, tmp_path / "work")
    assert len(res.steps) >= 30
    assert res.biomes_color.exists() and res.height_shaded.exists() and res.heightmap.exists()
    assert res.seconds > 0
    files = save_result(res, tmp_path / "saved")
    names = {p.name for p in files}
    assert {"config.yaml", "config.json", "heightmap.png", "biomes_color.png"} <= names
    assert json.loads((tmp_path / "saved" / "config.json").read_text(encoding="utf-8"))["seed"] == 3
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
