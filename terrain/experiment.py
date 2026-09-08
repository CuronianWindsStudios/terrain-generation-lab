"""Helpers for the experiment UI: build a config from flat values, generate, and save."""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

from terrain.config import Config, Profile, config_from_dict, config_to_dict
from terrain.debug import StepRecord
from terrain.export import hillshade
from terrain.heightmap import biome_noise
from terrain.pipeline import run_pipeline

PROFILE_FIELDS = ("base", "amplitude", "frequency", "octaves", "lacunarity", "persistence", "noise", "blend_px")


@dataclass
class ExperimentResult:
    config: Config
    out_dir: Path
    steps: list[StepRecord]
    biomes_color: Path
    biomes_type_color: Path
    height_shaded: Path
    heightmap: Path
    seconds: float
    seeds_used: dict


def build_overrides(values: dict) -> dict:
    """Map flat UI values to the nested config dict. Keys that are absent stay at the default."""
    v = dict(values)
    out: dict = {}

    def put(path: tuple[str, ...], value) -> None:
        node = out
        for key in path[:-1]:
            node = node.setdefault(key, {})
        node[path[-1]] = value

    simple = {
        "seed": ("seed",),
        "size": ("size",),
        "diameter": ("circle", "diameter_pct"),
        "threshold": ("landmass", "threshold"),
        "channel_pct": ("landmass", "channel_pct"),
        "warp_pct": ("landmass", "warp_pct"),
        "noise_frequency": ("landmass", "noise", "frequency"),
        "noise_octaves": ("landmass", "noise", "octaves"),
        "seed_area_pct": ("landmass", "seed_area_pct"),
        "min_separation_pct": ("landmass", "min_separation_pct"),
        "biome_warp_px": ("biomes", "warp", "strength_px"),
        "coast_band_px": ("biomes", "coast_band_px"),
        "balance_iterations": ("biomes", "balance_iterations"),
        "balance_tolerance": ("biomes", "balance_tolerance"),
        "coast_distance_px": ("heightmap", "coast_distance_px"),
        "seabed_depth": ("heightmap", "seabed_depth"),
        "spit_bay_pct": ("spit", "bay_pct"),
        "spit_lagoon_pct": ("spit", "lagoon_pct"),
        "spit_min_lagoon_pct": ("spit", "min_lagoon_pct"),
        "spit_width_pct": ("spit", "width_pct"),
        "spit_width_variation": ("spit", "width_variation"),
        "spit_strait_pct": ("spit", "strait_pct"),
        "spit_gap_pct": ("spit", "gap_pct"),
        "spit_edge_noise_pct": ("spit", "edge_noise_pct"),
        "spit_rise_px": ("spit", "rise_px"),
    }
    for key, path in simple.items():
        if key in v:
            put(path, v[key])
    if "radius_min" in v and "radius_max" in v:
        put(("landmass", "radius_pct"), [v["radius_min"], v["radius_max"]])
    if "seeds_min" in v and "seeds_max" in v:
        put(("biomes", "seeds_per_landmass"), [v["seeds_min"], v["seeds_max"]])
    if "spit_length_min" in v and "spit_length_max" in v:
        put(("spit", "length_pct"), [v["spit_length_min"], v["spit_length_max"]])
    for key, value in v.items():
        if not key.startswith("profile_"):
            continue
        body = key[len("profile_"):]  # <biome name>_<field>, the name can contain underscores
        for field_name in PROFILE_FIELDS:
            if body.endswith("_" + field_name):
                name = body[: -len(field_name) - 1]
                put(("heightmap", "profiles", name, field_name), value)
                break
    return out


def overrides_key(overrides: dict) -> str:
    text = json.dumps(overrides, sort_keys=True, default=str)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


def generate(overrides: dict, work_dir: str | Path, debug: bool = True) -> ExperimentResult:
    """Run the pipeline into work_dir/<key> and collect the paths the UI shows."""
    cfg = config_from_dict(overrides)
    out = Path(work_dir) / overrides_key(overrides)
    start = time.perf_counter()
    result = run_pipeline(cfg, out, debug=debug)
    seconds = time.perf_counter() - start
    return ExperimentResult(
        config=cfg,
        out_dir=out,
        steps=result.steps,
        biomes_color=out / "preview" / "biomes_color.png",
        biomes_type_color=out / "preview" / "biomes_type_color.png",
        height_shaded=out / "preview" / "height_shaded.png",
        heightmap=out / "preview" / "heightmap_8bit.png",
        seconds=seconds,
        seeds_used={"landmass": result.land.seed_used, "biomes": result.biomes.seed_used},
    )


def save_result(result: ExperimentResult, target_dir: str | Path) -> list[Path]:
    """Copy the Unreal files and the previews to target_dir and write config.yaml."""
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for sub in ("unreal", "preview"):
        src = result.out_dir / sub
        dst = target / sub
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        written += sorted(dst.iterdir())
    data = config_to_dict(result.config)
    cfg_path = target / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    written.append(cfg_path)
    json_path = target / "config.json"
    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    written.append(json_path)
    return written


def settings_json(overrides: dict) -> str:
    """The full config as JSON text: the defaults with the overrides applied."""
    return json.dumps(config_to_dict(config_from_dict(overrides)), indent=2)


ZIP_README = """Terrain export
==============

config.json / config.yaml   the settings of this world. Run them again with:
                            python -m terrain --config config.json
unreal/heightmap.png        16-bit heightmap. Sea level is at value 32768.
unreal/weight_<biome>.png   one layer weight map per biome type. They add up to 255 at each pixel.
unreal/subtype_<biome>_<A|B|C>.png   one mask per sub-type.
unreal/params.json          the seed, the settings, the region list, and the Unreal import settings.
preview/                    images for people: the hill shade, the biome maps, and an 8-bit heightmap.

Import into Unreal: open the Landscape mode, select Import from File, and pick unreal/heightmap.png.
Use the section size, the sections per component, and the components from unreal/params.json.
Import each weight_*.png as a layer.
"""


def export_zip(result: ExperimentResult) -> bytes:
    """A ZIP with the config as JSON and YAML, the Unreal files, and the previews."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        data = config_to_dict(result.config)
        zf.writestr("config.json", json.dumps(data, indent=2))
        zf.writestr("config.yaml", yaml.safe_dump(data, sort_keys=False))
        zf.writestr("README.txt", ZIP_README)
        for sub in ("unreal", "preview"):
            for path in sorted((result.out_dir / sub).iterdir()):
                zf.write(path, f"{sub}/{path.name}")
    return buffer.getvalue()


def profile_height_crop(profile: Profile, size: int, seed: int, biome_index: int, crop_px: int) -> np.ndarray:
    """The inland height of one biome, cropped at the center of the map.

    The crop uses the same noise field as the real map, so the scale is true. The coast curve
    is not applied. height = clamp(base + amplitude * noise, -1, 1).
    """
    noise = biome_noise(profile, size, seed, biome_index)
    crop = min(crop_px, size)
    start = (size - crop) // 2
    window = noise[start:start + crop, start:start + crop]
    height = profile.base + profile.amplitude * window
    return np.clip(height, -1.0, 1.0).astype(np.float32)


def profile_preview(profile: Profile, size: int, seed: int, biome_index: int, crop_px: int = 200) -> np.ndarray:
    """An 8-bit RGB hill shade of profile_height_crop. Higher land is brighter. Water is blue."""
    height = profile_height_crop(profile, size, seed, biome_index, crop_px)
    shade = hillshade(height, z_factor=size / 12.0)
    shaded = np.clip(0.65 * shade + 0.35 * np.clip(height, 0.0, 1.0), 0.0, 1.0)
    rgb = np.repeat(shaded[..., None], 3, axis=2)
    water = height < 0.0
    rgb[water] = rgb[water] * np.array([0.35, 0.55, 0.9]) + np.array([0.0, 0.05, 0.1])
    return np.round(np.clip(rgb, 0.0, 1.0) * 255.0).astype(np.uint8)
