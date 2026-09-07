"""Configuration dataclasses, YAML load, and validation."""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

UNREAL_SIZES = (127, 253, 505, 1009, 2017, 4033, 8129)
PLACEMENTS = ("coast", "low", "inland", "any")
SUBTYPE_LETTERS = ("A", "B", "C")


class ConfigError(ValueError):
    """A config value is out of range."""


class GenerationError(RuntimeError):
    """The pipeline cannot satisfy a rule after the retries."""


@dataclass
class NoiseConfig:
    octaves: int = 6
    frequency: float = 3.0
    lacunarity: float = 2.0
    persistence: float = 0.5


@dataclass
class CircleConfig:
    diameter_pct: float = 90.0
    edge_band_pct: float = 10.0


@dataclass
class LandmassConfig:
    count: int = 3
    seed_area_pct: float = 55.0
    min_separation_pct: float = 75.0
    radius_pct: tuple[float, float] = (100.0, 120.0)
    warp_pct: float = 15.0
    channel_pct: float = 22.0
    noise: NoiseConfig = field(default_factory=lambda: NoiseConfig(octaves=7, frequency=5.0))
    threshold: float = 0.28
    min_lake_area_px: int = 200
    max_retries: int = 10


@dataclass
class WarpConfig:
    strength_px: float = 90.0
    frequency: float = 5.0
    octaves: int = 5


@dataclass
class BiomeType:
    name: str
    label: str
    placement: str


def default_biome_types() -> list[BiomeType]:
    return [
        BiomeType("sea_side", "Sea Side (Neringa)", "coast"),
        BiomeType("marshlands", "Marshlands", "low"),
        BiomeType("ancient_grove", "Ancient Grove", "any"),
        BiomeType("enchanted_forest", "Enchanted Forest", "any"),
        BiomeType("mountain_range", "Mountain Range", "inland"),
    ]


@dataclass
class BiomesConfig:
    seeds_per_landmass: tuple[int, int] = (5, 7)
    min_seed_separation_px: float = 60.0
    coast_band_px: float = 40.0
    inland_fraction: float = 0.7
    max_retries: int = 10
    warp: WarpConfig = field(default_factory=WarpConfig)
    types: list[BiomeType] = field(default_factory=default_biome_types)


@dataclass
class Profile:
    base: float
    amplitude: float
    frequency: float
    octaves: int
    ridged: bool = False


def default_profiles() -> dict[str, Profile]:
    return {
        "sea_side": Profile(0.05, 0.04, 12.0, 3),
        "marshlands": Profile(0.03, 0.01, 6.0, 2),
        "ancient_grove": Profile(0.25, 0.12, 5.0, 5),
        "enchanted_forest": Profile(0.30, 0.15, 6.0, 5),
        "mountain_range": Profile(0.60, 0.40, 8.0, 6, ridged=True),
    }


@dataclass
class HeightmapConfig:
    coast_distance_px: float = 80.0
    coast_blur_px: float = 12.0
    profile_blur_px: float = 25.0
    profiles: dict[str, Profile] = field(default_factory=default_profiles)
    seabed_depth: float = 0.3
    seabed_distance_px: float = 150.0
    seabed_blur_px: float = 10.0


@dataclass
class ExportConfig:
    sea_level_value: int = 32768
    weight_blur_px: float = 12.0


@dataclass
class Config:
    seed: int = 42
    size: int = 1009
    circle: CircleConfig = field(default_factory=CircleConfig)
    landmass: LandmassConfig = field(default_factory=LandmassConfig)
    biomes: BiomesConfig = field(default_factory=BiomesConfig)
    heightmap: HeightmapConfig = field(default_factory=HeightmapConfig)
    export: ExportConfig = field(default_factory=ExportConfig)


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def config_to_dict(cfg: Config) -> dict:
    return asdict(cfg)


def config_from_dict(data: dict) -> Config:
    d = _merge(config_to_dict(Config()), data or {})
    lm = d["landmass"]
    bi = d["biomes"]
    hm = d["heightmap"]
    cfg = Config(
        seed=int(d["seed"]),
        size=int(d["size"]),
        circle=CircleConfig(**d["circle"]),
        landmass=LandmassConfig(
            count=int(lm["count"]),
            seed_area_pct=float(lm["seed_area_pct"]),
            min_separation_pct=float(lm["min_separation_pct"]),
            radius_pct=tuple(float(v) for v in lm["radius_pct"]),
            warp_pct=float(lm["warp_pct"]),
            channel_pct=float(lm["channel_pct"]),
            noise=NoiseConfig(**lm["noise"]),
            threshold=float(lm["threshold"]),
            min_lake_area_px=int(lm["min_lake_area_px"]),
            max_retries=int(lm["max_retries"]),
        ),
        biomes=BiomesConfig(
            seeds_per_landmass=tuple(int(v) for v in bi["seeds_per_landmass"]),
            min_seed_separation_px=float(bi["min_seed_separation_px"]),
            coast_band_px=float(bi["coast_band_px"]),
            inland_fraction=float(bi["inland_fraction"]),
            max_retries=int(bi["max_retries"]),
            warp=WarpConfig(**bi["warp"]),
            types=[BiomeType(**t) for t in bi["types"]],
        ),
        heightmap=HeightmapConfig(
            coast_distance_px=float(hm["coast_distance_px"]),
            coast_blur_px=float(hm["coast_blur_px"]),
            profile_blur_px=float(hm["profile_blur_px"]),
            profiles={k: Profile(**v) for k, v in hm["profiles"].items()},
            seabed_depth=float(hm["seabed_depth"]),
            seabed_distance_px=float(hm["seabed_distance_px"]),
            seabed_blur_px=float(hm["seabed_blur_px"]),
        ),
        export=ExportConfig(**d["export"]),
    )
    validate(cfg)
    return cfg


def validate(cfg: Config) -> None:
    if cfg.size not in UNREAL_SIZES:
        sizes = ", ".join(str(s) for s in UNREAL_SIZES)
        raise ConfigError(f"size must be one of {sizes}. Got {cfg.size}.")
    if not 0 < cfg.circle.diameter_pct <= 100:
        raise ConfigError(f"circle.diameter_pct must be in (0, 100]. Got {cfg.circle.diameter_pct}.")
    if cfg.landmass.count != 3:
        raise ConfigError(f"landmass.count must be 3 in this version. Got {cfg.landmass.count}.")
    if len(cfg.biomes.types) != 5:
        raise ConfigError(f"biomes.types must have 5 entries. Got {len(cfg.biomes.types)}.")
    for t in cfg.biomes.types:
        if t.placement not in PLACEMENTS:
            raise ConfigError(f"placement of biome {t.name} must be one of {PLACEMENTS}. Got {t.placement}.")
        if t.name not in cfg.heightmap.profiles:
            raise ConfigError(f"heightmap.profiles has no entry for biome {t.name}.")
    lo, hi = cfg.biomes.seeds_per_landmass
    if lo < len(cfg.biomes.types) or hi < lo:
        raise ConfigError(
            f"biomes.seeds_per_landmass must be [lo, hi] with lo >= 5 and hi >= lo. Got {lo}, {hi}."
        )
    if not 0 < cfg.heightmap.seabed_depth <= 1:
        raise ConfigError(f"heightmap.seabed_depth must be in (0, 1]. Got {cfg.heightmap.seabed_depth}.")


def load_config(path: str | Path | None = None, overrides: dict | None = None) -> Config:
    data: dict = {}
    if path is not None:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    if overrides:
        data = _merge(data, overrides)
    return config_from_dict(data)
