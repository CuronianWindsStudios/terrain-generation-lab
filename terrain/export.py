"""Stage 5: Unreal Engine files and previews."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy import ndimage

from terrain.biomes import BiomeResult
from terrain.config import SUBTYPE_LETTERS, Config, config_to_dict
from terrain.heightmap import HeightResult
from terrain.imageio import save_gray8, save_gray16, save_rgb
from terrain.landmass import LandResult

PALETTE = [
    (224, 200, 120),  # sea_side: sand
    (107, 142, 35),   # marshlands: olive
    (46, 107, 58),    # ancient_grove: deep green
    (122, 79, 163),   # enchanted_forest: violet
    (140, 140, 140),  # mountain_range: gray
]
SEA_COLOR = (26, 58, 107)
SUBTYPE_LIGHTNESS = (0.75, 1.0, 1.25)


def encode_height16(height: np.ndarray, sea_level_value: int) -> np.ndarray:
    sea = float(sea_level_value)
    above = sea + height * (65535.0 - sea)
    below = sea + height * sea
    out = np.where(height >= 0.0, above, below)
    return np.clip(np.round(out), 0, 65535).astype(np.uint16)


def largest_remainder_255(weights: np.ndarray) -> np.ndarray:
    """Quantize weights that sum to 1 along axis 0 into uint8 values that sum to exactly 255."""
    scaled = weights * 255.0
    base = np.floor(scaled)
    frac = scaled - base
    missing = (255 - base.sum(axis=0)).astype(np.int64)
    rank = np.argsort(np.argsort(-frac, axis=0, kind="stable"), axis=0, kind="stable")
    add = rank < missing[None, ...]
    return (base + add).astype(np.uint8)


def make_weight_maps(biome_ids: np.ndarray, land_mask: np.ndarray, n_types: int,
                     blur_px: float, seabed_index: int = 0) -> np.ndarray:
    """One weight map per biome type. Sea pixels near the coast take the nearest land biome.
    Further out, the sea blends to the seabed biome (the coast biome, sand)."""
    sea_distance, idx = ndimage.distance_transform_edt(~land_mask, return_indices=True)
    filled = biome_ids[idx[0], idx[1]]
    onehot = np.stack([(filled == i + 1) for i in range(n_types)]).astype(np.float32)
    shelf_px = max(4.0 * blur_px, 1.0)
    t = (sea_distance / shelf_px).clip(0.0, 1.0).astype(np.float32)
    t = t * t * (3.0 - 2.0 * t)
    seabed = np.zeros_like(onehot)
    seabed[seabed_index] = 1.0
    onehot = onehot * (1.0 - t)[None] + seabed * t[None]
    blurred = ndimage.gaussian_filter(onehot, sigma=(0.0, blur_px, blur_px))
    weights = blurred / np.maximum(blurred.sum(axis=0, keepdims=True), 1e-6)
    return largest_remainder_255(weights)


def unreal_import_settings(size: int, sea_level_value: int) -> dict:
    components = (size - 1) // 126
    return {
        "resolution": size,
        "section_size": "63x63",
        "sections_per_component": "2x2",
        "components": f"{components}x{components}",
        "z_scale": 100,
        "sea_level_value": sea_level_value,
        "note": "With z_scale 100, value 32768 is 0 m, 65535 is +256 m, and 0 is -256 m. "
                "Import heightmap.png as the landscape heightmap. Import each weight_*.png as a layer.",
    }


def export_unreal(cfg: Config, land: LandResult, biomes: BiomeResult, height: HeightResult,
                  out_dir: str | Path, seeds_used: dict) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    n_types = len(cfg.biomes.types)
    n_sub = len(SUBTYPE_LETTERS)

    files.append(save_gray16(out / "heightmap.png",
                             encode_height16(height.height, cfg.export.sea_level_value)))

    coast_types = [i for i, t in enumerate(cfg.biomes.types) if t.placement == "coast"]
    seabed_index = coast_types[0] if coast_types else 0
    weights = make_weight_maps(biomes.biome_ids, land.land_mask, n_types,
                               cfg.export.weight_blur_px, seabed_index)
    for i, t in enumerate(cfg.biomes.types):
        files.append(save_gray8(out / f"weight_{t.name}.png", weights[i]))

    for i, t in enumerate(cfg.biomes.types):
        for s, letter in enumerate(SUBTYPE_LETTERS):
            sid = i * n_sub + s + 1
            mask = np.where(biomes.subtype_ids == sid, 255, 0).astype(np.uint8)
            files.append(save_gray8(out / f"subtype_{t.name}_{letter}.png", mask))

    params = {
        "seed": cfg.seed,
        "seeds_used": seeds_used,
        "config": config_to_dict(cfg),
        "biome_ids": {i + 1: t.label for i, t in enumerate(cfg.biomes.types)},
        "subtype_ids": {i * n_sub + s + 1: f"{t.label} {letter}"
                        for i, t in enumerate(cfg.biomes.types)
                        for s, letter in enumerate(SUBTYPE_LETTERS)},
        "regions": [{"id": r.id, "landmass": r.landmass_id,
                     "biome": cfg.biomes.types[r.biome_index].name,
                     "subtype": SUBTYPE_LETTERS[r.subtype_index],
                     "seed_xy": [round(r.seed_xy[0]), round(r.seed_xy[1])]} for r in biomes.regions],
        "unreal_import": unreal_import_settings(cfg.size, cfg.export.sea_level_value),
    }
    path = out / "params.json"
    path.write_text(json.dumps(params, indent=2), encoding="utf-8")
    files.append(path)
    return files


def hillshade(height: np.ndarray, z_factor: float, azimuth_deg: float = 315.0,
              altitude_deg: float = 45.0) -> np.ndarray:
    dy, dx = np.gradient(height.astype(np.float64) * z_factor)
    zenith = np.radians(90.0 - altitude_deg)
    azimuth = np.radians(360.0 - azimuth_deg + 90.0)
    slope = np.arctan(np.hypot(dx, dy))
    aspect = np.arctan2(dy, -dx)
    shade = np.cos(zenith) * np.cos(slope) + np.sin(zenith) * np.sin(slope) * np.cos(azimuth - aspect)
    return np.clip(shade, 0.0, 1.0)


def write_previews(cfg: Config, biomes: BiomeResult, height: HeightResult,
                   out_dir: str | Path) -> list[Path]:
    out = Path(out_dir)
    h = height.height
    size = h.shape[0]
    shade = hillshade(h, z_factor=size / 12.0)
    norm = (h - h.min()) / max(float(h.max() - h.min()), 1e-6)
    shaded = np.clip(0.65 * shade + 0.35 * norm, 0.0, 1.0)
    shaded[h < 0.0] *= 0.6
    files = [save_gray8(out / "height_shaded.png", np.round(shaded * 255.0).astype(np.uint8))]
    height8 = (encode_height16(h, cfg.export.sea_level_value) >> 8).astype(np.uint8)
    files.append(save_gray8(out / "heightmap_8bit.png", height8))

    files.append(save_rgb(out / "biomes_color.png", biome_color_image(cfg, biomes, shade, subtypes=True)))
    files.append(save_rgb(out / "biomes_type_color.png", biome_color_image(cfg, biomes, shade, subtypes=False)))
    return files


def biome_color(biome_index: int, subtype_index: int | None = None) -> tuple[int, int, int]:
    """The preview color of a biome type, or of one of its sub-types."""
    base = np.array(PALETTE[biome_index % len(PALETTE)], dtype=np.float32)
    if subtype_index is not None:
        base = base * SUBTYPE_LIGHTNESS[subtype_index]
    return tuple(int(v) for v in np.clip(base, 0, 255))


def biome_color_image(cfg: Config, biomes: BiomeResult, shade: np.ndarray, subtypes: bool) -> np.ndarray:
    """RGB map of the biomes. With subtypes, each sub-type A, B, C gets its own lightness."""
    size = biomes.biome_ids.shape[0]
    rgb = np.zeros((size, size, 3), dtype=np.float32)
    rgb[...] = SEA_COLOR
    n_sub = len(SUBTYPE_LETTERS)
    for i in range(len(cfg.biomes.types)):
        if subtypes:
            for s in range(n_sub):
                sid = i * n_sub + s + 1
                rgb[biomes.subtype_ids == sid] = biome_color(i, s)
        else:
            rgb[biomes.biome_ids == i + 1] = biome_color(i)
    land = biomes.biome_ids > 0
    rgb[land] = rgb[land] * (0.6 + 0.4 * shade[land][:, None])
    return np.clip(rgb, 0, 255).astype(np.uint8)
