"""Configuration dataclasses, YAML load, and validation."""
from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

UNREAL_SIZES = (127, 253, 505, 1009, 2017, 4033, 8129)
PLACEMENTS = ("spit", "coast", "low", "inland", "any")
SUBTYPE_LETTERS = ("A", "B", "C")
NOISE_TYPES = ("fractal", "ridged", "billow")


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
        BiomeType("sea_side", "Sea Side (Neringa)", "spit"),
        BiomeType("marshlands", "Marshlands", "low"),
        BiomeType("ancient_grove", "Ancient Grove", "any"),
        BiomeType("enchanted_forest", "Enchanted Forest", "any"),
        BiomeType("mountain_range", "Mountain Range", "inland"),
    ]


@dataclass
class BiomesConfig:
    seeds_per_landmass: tuple[int, int] = (4, 6)
    min_seed_separation_px: float = 60.0
    coast_band_px: float = 40.0
    inland_fraction: float = 0.7
    max_retries: int = 10
    balance_iterations: int = 25      # bias tuning rounds so the mainland biomes share each land equally
    balance_tolerance: float = 0.05   # allowed difference from the equal share, as a fraction of the land
    warp: WarpConfig = field(default_factory=WarpConfig)
    types: list[BiomeType] = field(default_factory=default_biome_types)


@dataclass
class SpitConfig:
    """One sand bar per landmass. The bar runs along the coast at the lagoon distance and joins the
    coast at both ends. It crosses the bay mouths, so the bays become lagoons.

    The sizes marked pct are a percentage of the circle radius, except min_lagoon_pct, which is a
    percentage of the landmass area. So every image size gives the same shape.
    """
    bay_pct: float = 15.0             # disk size of the bay search: bays narrower than 2x this are crossed
    lagoon_pct: float = 5.0           # width of the water behind the bar
    length_pct: tuple[float, float] = (40.0, 90.0)  # bar length, random in this range
    min_lagoon_pct: float = 3.0       # smallest lagoon area, % of the landmass area
    width_pct: float = 4.0            # base width of the bar
    width_variation: float = 0.5      # the width varies by this fraction along the bar
    strait_pct: float = 2.5           # opening near one end. 0 closes the lagoon
    edge_noise_pct: float = 1.0
    gap_pct: float = 6.0              # smallest distance to other land
    rise_px: float = 6.0


@dataclass
class Profile:
    """The height profile of one biome type. height = base + amplitude * noise, noise in [0, 1]."""
    base: float
    amplitude: float
    frequency: float
    octaves: int
    lacunarity: float = 2.0
    persistence: float = 0.5
    noise: str = "fractal"
    blend_px: float = 25.0


def default_profiles() -> dict[str, Profile]:
    return {
        "sea_side": Profile(0.01, 0.08, 12.0, 3),
        "marshlands": Profile(-0.03, 0.12, 6.0, 2),
        "ancient_grove": Profile(0.13, 0.24, 5.0, 5),
        "enchanted_forest": Profile(0.15, 0.30, 6.0, 5),
        "mountain_range": Profile(0.20, 0.80, 8.0, 6, noise="ridged"),
    }


@dataclass
class HeightmapConfig:
    coast_distance_px: float = 80.0
    coast_blur_px: float = 12.0
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
    spit: SpitConfig = field(default_factory=SpitConfig)
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
    sp = d["spit"]
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
            balance_iterations=int(bi["balance_iterations"]),
            balance_tolerance=float(bi["balance_tolerance"]),
            warp=WarpConfig(**bi["warp"]),
            types=[BiomeType(**t) for t in bi["types"]],
        ),
        spit=SpitConfig(**{k: (tuple(float(x) for x in v) if k == "length_pct" else float(v))
                           for k, v in sp.items()}),
        heightmap=HeightmapConfig(
            coast_distance_px=float(hm["coast_distance_px"]),
            coast_blur_px=float(hm["coast_blur_px"]),
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
    n_seeded = sum(1 for t in cfg.biomes.types if t.placement != "spit")
    if lo < n_seeded or hi < lo:
        raise ConfigError(
            f"biomes.seeds_per_landmass must be [lo, hi] with lo >= {n_seeded} and hi >= lo. Got {lo}, {hi}."
        )
    if cfg.biomes.balance_iterations < 0:
        raise ConfigError(f"biomes.balance_iterations must be >= 0. Got {cfg.biomes.balance_iterations}.")
    if not 0 < cfg.biomes.balance_tolerance < 1:
        raise ConfigError(f"biomes.balance_tolerance must be in (0, 1). Got {cfg.biomes.balance_tolerance}.")
    sp = cfg.spit
    if not 0 < sp.length_pct[0] <= sp.length_pct[1]:
        raise ConfigError(f"spit.length_pct must be [lo, hi] with 0 < lo <= hi. Got {list(sp.length_pct)}.")
    if sp.bay_pct < 0:
        raise ConfigError(f"spit.bay_pct must be >= 0. Got {sp.bay_pct}.")
    if sp.lagoon_pct <= 0:
        raise ConfigError(f"spit.lagoon_pct must be > 0. Got {sp.lagoon_pct}.")
    if sp.min_lagoon_pct <= 0:
        raise ConfigError(f"spit.min_lagoon_pct must be > 0. Got {sp.min_lagoon_pct}.")
    if sp.width_pct <= 0:
        raise ConfigError(f"spit.width_pct must be > 0. Got {sp.width_pct}.")
    if not 0 <= sp.width_variation < 1:
        raise ConfigError(f"spit.width_variation must be in [0, 1). Got {sp.width_variation}.")
    if sp.rise_px <= 0:
        raise ConfigError(f"spit.rise_px must be > 0. Got {sp.rise_px}.")
    if sp.strait_pct < 0 or sp.gap_pct < 0 or sp.edge_noise_pct < 0:
        raise ConfigError("spit.strait_pct, spit.gap_pct, and spit.edge_noise_pct must be >= 0.")
    for name, p in cfg.heightmap.profiles.items():
        prefix = f"heightmap.profiles.{name}"
        if not -1 <= p.base <= 1:
            raise ConfigError(f"{prefix}.base must be in [-1, 1]. Got {p.base}.")
        if p.amplitude < 0:
            raise ConfigError(f"{prefix}.amplitude must be >= 0. Got {p.amplitude}.")
        if p.octaves < 1:
            raise ConfigError(f"{prefix}.octaves must be >= 1. Got {p.octaves}.")
        if p.noise not in NOISE_TYPES:
            raise ConfigError(f"{prefix}.noise must be one of {NOISE_TYPES}. Got {p.noise}.")
        if p.blend_px <= 0:
            raise ConfigError(f"{prefix}.blend_px must be > 0. Got {p.blend_px}.")
        if p.lacunarity <= 0:
            raise ConfigError(f"{prefix}.lacunarity must be > 0. Got {p.lacunarity}.")
        if not 0 < p.persistence <= 1:
            raise ConfigError(f"{prefix}.persistence must be in (0, 1]. Got {p.persistence}.")
    if not 0 < cfg.heightmap.seabed_depth <= 1:
        raise ConfigError(f"heightmap.seabed_depth must be in (0, 1]. Got {cfg.heightmap.seabed_depth}.")


def load_config(path: str | Path | None = None, overrides: dict | None = None) -> Config:
    data: dict = {}
    if path is not None:
        with open(path, "r", encoding="utf-8") as fh:
            if str(path).lower().endswith(".json"):
                data = json.load(fh) or {}
            else:
                data = yaml.safe_load(fh) or {}
    if overrides:
        data = _merge(data, overrides)
    return config_from_dict(data)
