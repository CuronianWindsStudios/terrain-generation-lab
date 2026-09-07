"""Helpers for the experiment UI: build a config from flat values, generate, and save."""
from __future__ import annotations

import hashlib
import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

import yaml

from terrain.config import Config, config_from_dict, config_to_dict
from terrain.debug import StepRecord
from terrain.pipeline import run_pipeline

PROFILE_FIELDS = ("base", "amplitude")


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
        "coast_distance_px": ("heightmap", "coast_distance_px"),
        "profile_blur_px": ("heightmap", "profile_blur_px"),
        "seabed_depth": ("heightmap", "seabed_depth"),
    }
    for key, path in simple.items():
        if key in v:
            put(path, v[key])
    if "radius_min" in v and "radius_max" in v:
        put(("landmass", "radius_pct"), [v["radius_min"], v["radius_max"]])
    if "seeds_min" in v and "seeds_max" in v:
        put(("biomes", "seeds_per_landmass"), [v["seeds_min"], v["seeds_max"]])
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
    cfg_path = target / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(config_to_dict(result.config), sort_keys=False), encoding="utf-8")
    written.append(cfg_path)
    return written
