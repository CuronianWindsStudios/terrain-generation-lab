import json

import numpy as np

from terrain.biomes import make_biomes
from terrain.circle import make_circle
from terrain.config import config_from_dict
from terrain.debug import StepRecorder
from terrain.export import (
    encode_height16,
    export_unreal,
    largest_remainder_255,
    make_weight_maps,
    unreal_import_settings,
    write_previews,
)
from terrain.heightmap import make_heightmap
from terrain.imageio import load_array
from terrain.landmass import make_landmasses

SIZE = 253


def _world():
    cfg = config_from_dict({"size": SIZE})
    rec = StepRecorder(None, False)
    circle = make_circle(cfg.size, cfg.circle, rec)
    land = make_landmasses(circle, cfg.landmass, cfg.seed, rec)
    biomes = make_biomes(land, cfg.biomes, cfg.seed, rec)
    height = make_heightmap(circle, land, biomes, cfg.heightmap, cfg.seed, rec)
    return cfg, land, biomes, height


def test_encode_height16():
    h = np.array([[-1.0, -0.5, 0.0, 0.5, 1.0]], dtype=np.float32)
    out = encode_height16(h, 32768)
    assert out.dtype == np.uint16
    assert out.tolist() == [[0, 16384, 32768, 49152, 65535]]


def test_largest_remainder_sums_to_255():
    rng = np.random.default_rng(0)
    w = rng.random((5, 8, 8)).astype(np.float32)
    w /= w.sum(0, keepdims=True)
    q = largest_remainder_255(w)
    assert q.dtype == np.uint8
    assert np.all(q.sum(0, dtype=np.int32) == 255)


def test_weight_maps_cover_sea_and_sum_to_255():
    cfg, land, biomes, height = _world()
    w = make_weight_maps(biomes.biome_ids, land.land_mask, 5, cfg.export.weight_blur_px)
    assert w.shape == (5, SIZE, SIZE)
    assert np.all(w.sum(0, dtype=np.int32) == 255)


def test_unreal_import_settings():
    s = unreal_import_settings(1009, 32768)
    assert s["components"] == "8x8"
    assert unreal_import_settings(253, 32768)["components"] == "2x2"


def test_export_files(tmp_path):
    cfg, land, biomes, height = _world()
    files = export_unreal(cfg, land, biomes, height, tmp_path / "unreal", {"landmass": 42, "biomes": 42})
    names = sorted(p.name for p in files)
    assert "heightmap.png" in names
    assert sum(n.startswith("weight_") for n in names) == 5
    assert sum(n.startswith("subtype_") for n in names) == 15
    assert "params.json" in names
    hm = load_array(tmp_path / "unreal" / "heightmap.png")
    assert hm.dtype == np.uint16 and hm.shape == (SIZE, SIZE)
    coast = land.land_mask & (biomes.coast_distance <= 1.0)
    assert np.all(np.abs(hm[coast].astype(np.int64) - 32768) < 700)
    params = json.loads((tmp_path / "unreal" / "params.json").read_text(encoding="utf-8"))
    assert params["seed"] == 42
    assert params["unreal_import"]["resolution"] == SIZE
    previews = write_previews(cfg, biomes, height, tmp_path / "preview")
    assert sorted(p.name for p in previews) == ["biomes_color.png", "height_shaded.png", "heightmap_8bit.png"]
