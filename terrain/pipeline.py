"""Runs the five stages in order."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from terrain.biomes import BiomeResult, make_biomes
from terrain.circle import CircleResult, make_circle
from terrain.config import Config
from terrain.debug import StepRecord, StepRecorder
from terrain.export import export_unreal, write_previews
from terrain.heightmap import HeightResult, make_heightmap
from terrain.landmass import LandResult, make_landmasses


@dataclass
class PipelineResult:
    config: Config
    circle: CircleResult
    land: LandResult
    biomes: BiomeResult
    height: HeightResult
    files: list[Path]
    walkthrough: Path | None
    steps: list[StepRecord] = field(default_factory=list)


def run_pipeline(cfg: Config, out_dir: str | Path, debug: bool = False) -> PipelineResult:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    recorder = StepRecorder(out, debug)
    circle = make_circle(cfg.size, cfg.circle, recorder)
    land = make_landmasses(circle, cfg.landmass, cfg.seed, recorder, cfg.spit)
    biomes = make_biomes(land, cfg.biomes, cfg.seed, recorder)
    height = make_heightmap(circle, land, biomes, cfg.heightmap, cfg.seed, recorder, cfg.spit.rise_px)
    seeds_used = {"landmass": land.seed_used, "biomes": biomes.seed_used}
    files = export_unreal(cfg, land, biomes, height, out / "unreal", seeds_used)
    files += write_previews(cfg, biomes, height, out / "preview")
    walkthrough = recorder.write_walkthrough()
    return PipelineResult(cfg, circle, land, biomes, height, files, walkthrough, list(recorder.records))
