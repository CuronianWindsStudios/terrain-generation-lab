# Terrain Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python command line tool that generates a circular world with 3 landmasses, 5 biome types with 3 sub-types each, a 16-bit Unreal heightmap, biome weight maps, and a step-by-step walkthrough with one debug image per sub-step.

**Architecture:** One package `terrain/` with one module per pipeline stage. Each stage is a pure function over numpy arrays that returns a result dataclass and records sub-step images through a `StepRecorder`. Only `imageio.py`, `debug.py`, and `export.py` write files. A `pipeline.py` runs the stages in order and the CLI wraps it.

**Tech Stack:** Python 3.12, numpy, scipy (ndimage), Pillow, PyYAML, pytest.

**Spec:** `docs/superpowers/specs/2026-09-07-terrain-generator-design.md`

## Global Constraints

- `size` must be one of the Unreal sizes `127, 253, 505, 1009, 2017, 4033, 8129`. Default `1009`.
- Exactly 3 landmasses. Exactly 5 biome types. 3 sub-types per biome type (A, B, C), 15 in total.
- Heightmap: 16-bit grayscale PNG, sea level at value `32768`.
- Biome masks: 8-bit grayscale PNG. The 5 weight maps add up to 255 at each pixel.
- Determinism: each stage uses `numpy.random.default_rng([seed, stage_number, try_number])`. The same seed gives the same bytes.
- Stage functions do not read or write files. They call `recorder.step(...)` for each sub-step.
- User-facing text (walkthrough descriptions, README, error messages) is written in Simplified Technical English.
- Commit after each task. Commit messages end with the Co-Authored-By and Claude-Session trailers.

---

### Task 1: Project scaffold and configuration

**Files:**
- Create: `requirements.txt`, `pytest.ini`, `terrain/__init__.py`, `terrain/config.py`, `config.yaml`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Config`, `CircleConfig`, `LandmassConfig`, `BiomesConfig`, `BiomeType`, `HeightmapConfig`, `Profile`, `ExportConfig`, `NoiseConfig`, `WarpConfig`, `ConfigError`, `GenerationError`, `UNREAL_SIZES`, `SUBTYPE_LETTERS`, `load_config(path, overrides) -> Config`, `config_from_dict(dict) -> Config`, `config_to_dict(Config) -> dict`, `validate(Config)`.

- [ ] **Step 1: Write requirements and pytest config**

`requirements.txt`:
```
numpy>=2.0
Pillow>=10.0
scipy>=1.12
PyYAML>=6.0
pytest>=8.0
```

`pytest.ini`:
```ini
[pytest]
testpaths = tests
```

Run: `pip install -r requirements.txt`

- [ ] **Step 2: Write the failing tests**

`tests/test_config.py`:
```python
import pytest

from terrain.config import (
    Config,
    ConfigError,
    config_from_dict,
    config_to_dict,
    load_config,
)


def test_defaults_are_valid():
    cfg = config_from_dict({})
    assert cfg.size == 1009
    assert cfg.landmass.count == 3
    assert len(cfg.biomes.types) == 5
    assert set(cfg.heightmap.profiles) == {t.name for t in cfg.biomes.types}


def test_override_merges_nested_values():
    cfg = config_from_dict({"size": 253, "landmass": {"threshold": 0.3}})
    assert cfg.size == 253
    assert cfg.landmass.threshold == 0.3
    assert cfg.landmass.count == 3


def test_invalid_size_raises():
    with pytest.raises(ConfigError, match="127, 253, 505, 1009"):
        config_from_dict({"size": 1000})


def test_missing_profile_raises():
    types = config_to_dict(Config())["biomes"]["types"]
    types[0]["name"] = "lagoon"
    with pytest.raises(ConfigError, match="lagoon"):
        config_from_dict({"biomes": {"types": types}})


def test_load_yaml_and_cli_override(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("size: 505\nseed: 7\n", encoding="utf-8")
    cfg = load_config(path, {"seed": 9})
    assert cfg.size == 505
    assert cfg.seed == 9


def test_round_trip_dict():
    cfg = Config()
    again = config_from_dict(config_to_dict(cfg))
    assert config_to_dict(again) == config_to_dict(cfg)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'terrain'`

- [ ] **Step 4: Write the config module**

`terrain/__init__.py`:
```python
"""Circular world terrain generator for Unreal Engine."""
```

`terrain/config.py`:
```python
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
    seed_area_pct: float = 50.0
    min_separation_pct: float = 70.0
    radius_pct: tuple[float, float] = (45.0, 55.0)
    noise: NoiseConfig = field(default_factory=NoiseConfig)
    noise_strength: float = 0.45
    threshold: float = 0.4
    min_lake_area_px: int = 200
    max_retries: int = 10


@dataclass
class WarpConfig:
    strength_px: float = 60.0
    frequency: float = 4.0
    octaves: int = 4


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
        "mountain_range": Profile(0.60, 0.40, 4.0, 6, ridged=True),
    }


@dataclass
class HeightmapConfig:
    coast_distance_px: float = 120.0
    profile_blur_px: float = 25.0
    profiles: dict[str, Profile] = field(default_factory=default_profiles)
    seabed_depth: float = 0.3
    seabed_distance_px: float = 150.0


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
            noise=NoiseConfig(**lm["noise"]),
            noise_strength=float(lm["noise_strength"]),
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
            profile_blur_px=float(hm["profile_blur_px"]),
            profiles={k: Profile(**v) for k, v in hm["profiles"].items()},
            seabed_depth=float(hm["seabed_depth"]),
            seabed_distance_px=float(hm["seabed_distance_px"]),
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
        raise ConfigError(f"biomes.seeds_per_landmass must be [lo, hi] with lo >= 5 and hi >= lo. Got {lo}, {hi}.")
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
```

- [ ] **Step 5: Write `config.yaml` with the defaults**

Copy the YAML block from spec section 6, but with the tuned landmass defaults:
`seed_area_pct: 50`, `radius_pct: [45, 55]`, `threshold: 0.4`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: 6 PASS

- [ ] **Step 7: Commit**

```bash
git add requirements.txt pytest.ini terrain/ config.yaml tests/test_config.py
git commit -m "Add project scaffold and configuration"
```

---

### Task 2: Noise

**Files:**
- Create: `terrain/noise.py`
- Test: `tests/test_noise.py`

**Interfaces:**
- Produces: `smoothstep(x)`, `value_noise(shape, frequency, rng)`, `fractal_noise(shape, octaves, frequency, lacunarity, persistence, rng)`, `ridged_noise(shape, octaves, frequency, lacunarity, persistence, rng)`. All return `float32` arrays in `[0, 1]`.

- [ ] **Step 1: Write the failing tests**

`tests/test_noise.py`:
```python
import numpy as np

from terrain.noise import fractal_noise, ridged_noise, smoothstep, value_noise


def test_smoothstep_ends():
    assert smoothstep(np.float32(0.0)) == 0.0
    assert smoothstep(np.float32(1.0)) == 1.0
    assert abs(smoothstep(np.float32(0.5)) - 0.5) < 1e-6


def test_value_noise_shape_and_range():
    rng = np.random.default_rng(1)
    n = value_noise((64, 96), 3.0, rng)
    assert n.shape == (64, 96)
    assert n.dtype == np.float32
    assert n.min() >= 0.0 and n.max() <= 1.0


def test_fractal_noise_range_and_determinism():
    a = fractal_noise((64, 64), 5, 3.0, 2.0, 0.5, np.random.default_rng(3))
    b = fractal_noise((64, 64), 5, 3.0, 2.0, 0.5, np.random.default_rng(3))
    assert a.min() >= 0.0 and a.max() <= 1.0
    assert np.array_equal(a, b)
    assert a.std() > 0.01


def test_ridged_noise_range():
    n = ridged_noise((64, 64), 4, 4.0, 2.0, 0.5, np.random.default_rng(5))
    assert n.min() >= 0.0 and n.max() <= 1.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_noise.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'terrain.noise'`

- [ ] **Step 3: Write the noise module**

`terrain/noise.py`:
```python
"""Value noise, fractal noise, and ridged noise in numpy."""
from __future__ import annotations

import numpy as np


def smoothstep(x):
    return x * x * (3.0 - 2.0 * x)


def value_noise(shape: tuple[int, int], frequency: float, rng: np.random.Generator) -> np.ndarray:
    """Random lattice with smoothstep interpolation. Returns float32 in [0, 1]."""
    h, w = shape
    n = int(np.ceil(frequency)) + 2
    lattice = rng.random((n, n), dtype=np.float32)
    ys = np.linspace(0.0, frequency, h, endpoint=False, dtype=np.float32)
    xs = np.linspace(0.0, frequency, w, endpoint=False, dtype=np.float32)
    y0 = np.floor(ys).astype(np.int64)
    x0 = np.floor(xs).astype(np.int64)
    ty = smoothstep(ys - y0)[:, None]
    tx = smoothstep(xs - x0)[None, :]
    a = lattice[np.ix_(y0, x0)]
    b = lattice[np.ix_(y0, x0 + 1)]
    c = lattice[np.ix_(y0 + 1, x0)]
    d = lattice[np.ix_(y0 + 1, x0 + 1)]
    top = a + (b - a) * tx
    bottom = c + (d - c) * tx
    return (top + (bottom - top) * ty).astype(np.float32)


def _octaves(shape, octaves, frequency, lacunarity, persistence, rng, transform):
    total = np.zeros(shape, dtype=np.float32)
    amplitude = 1.0
    amplitude_sum = 0.0
    freq = frequency
    for _ in range(octaves):
        total += amplitude * transform(value_noise(shape, freq, rng))
        amplitude_sum += amplitude
        amplitude *= persistence
        freq *= lacunarity
    return (total / amplitude_sum).astype(np.float32)


def fractal_noise(shape, octaves, frequency, lacunarity, persistence, rng) -> np.ndarray:
    """Sum of value noise octaves. Returns float32 in [0, 1]."""
    return _octaves(shape, octaves, frequency, lacunarity, persistence, rng, lambda v: v)


def ridged_noise(shape, octaves, frequency, lacunarity, persistence, rng) -> np.ndarray:
    """Sum of ridged octaves, 1 - |2n - 1|. Makes sharp crests. Returns float32 in [0, 1]."""
    return _octaves(
        shape, octaves, frequency, lacunarity, persistence, rng,
        lambda v: 1.0 - np.abs(2.0 * v - 1.0),
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_noise.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add terrain/noise.py tests/test_noise.py
git commit -m "Add numpy value noise, fractal noise, and ridged noise"
```

---

### Task 3: Image I/O and the step recorder

**Files:**
- Create: `terrain/imageio.py`, `terrain/debug.py`
- Test: `tests/test_debug.py`

**Interfaces:**
- Produces: `to_uint8(array) -> uint8 array`, `save_gray8(path, uint8)`, `save_gray16(path, uint16)`, `save_rgb(path, uint8 HxWx3)`, `load_array(path) -> ndarray`.
- Produces: `StepRecorder(out_dir, enabled)` with `step(step_id, title, array, description, params=None)`, `note(step_id, title, description, params=None)`, `write_walkthrough() -> Path | None`, `records: list[StepRecord]`.

- [ ] **Step 1: Write the failing tests**

`tests/test_debug.py`:
```python
import numpy as np

from terrain.debug import StepRecorder
from terrain.imageio import load_array, save_gray16, to_uint8


def test_to_uint8_bool_and_float():
    assert to_uint8(np.array([[True, False]])).tolist() == [[255, 0]]
    out = to_uint8(np.array([[0.0, 0.5, 1.0]], dtype=np.float32))
    assert out.tolist() == [[0, 128, 255]]
    flat = to_uint8(np.zeros((2, 2), dtype=np.float32))
    assert flat.max() == 0


def test_save_gray16_round_trip(tmp_path):
    arr = np.array([[0, 32768], [65535, 1]], dtype=np.uint16)
    path = tmp_path / "h.png"
    save_gray16(path, arr)
    back = load_array(path)
    assert back.dtype == np.uint16
    assert np.array_equal(back, arr)


def test_recorder_disabled_writes_nothing(tmp_path):
    rec = StepRecorder(tmp_path, enabled=False)
    rec.step("01a", "Center distance", np.zeros((4, 4)), "text")
    assert rec.write_walkthrough() is None
    assert not (tmp_path / "steps").exists()


def test_recorder_writes_image_and_walkthrough(tmp_path):
    rec = StepRecorder(tmp_path, enabled=True)
    rec.step("01a", "Center distance", np.zeros((4, 4)), "The distance from the center.", {"size": 4})
    rec.note("02-retry-0", "Retry", "Try 1 gave 2 landmasses.", {"count": 2})
    path = rec.write_walkthrough()
    assert (tmp_path / "steps" / "01a_center_distance.png").exists()
    text = path.read_text(encoding="utf-8")
    assert "## Step 01a: Center distance" in text
    assert "| size | 4 |" in text
    assert "![Step 01a](steps/01a_center_distance.png)" in text
    assert "## Step 02-retry-0: Retry" in text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_debug.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the image I/O module**

`terrain/imageio.py`:
```python
"""Save and load grayscale and RGB PNG files."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def to_uint8(array: np.ndarray) -> np.ndarray:
    """Normalize any 2-D array to 0..255. Bool maps to 0/255. Others map min..max to 0..255."""
    if array.dtype == np.bool_:
        return np.where(array, 255, 0).astype(np.uint8)
    a = array.astype(np.float64)
    lo, hi = float(a.min()), float(a.max())
    if hi <= lo:
        return np.zeros(a.shape, dtype=np.uint8)
    return np.round((a - lo) / (hi - lo) * 255.0).astype(np.uint8)


def _prepare(path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def save_gray8(path: str | Path, array: np.ndarray) -> Path:
    p = _prepare(path)
    Image.fromarray(np.ascontiguousarray(array, dtype=np.uint8), mode="L").save(p)
    return p


def save_gray16(path: str | Path, array: np.ndarray) -> Path:
    p = _prepare(path)
    Image.fromarray(np.ascontiguousarray(array, dtype=np.uint16)).save(p)
    return p


def save_rgb(path: str | Path, array: np.ndarray) -> Path:
    p = _prepare(path)
    Image.fromarray(np.ascontiguousarray(array, dtype=np.uint8), mode="RGB").save(p)
    return p


def load_array(path: str | Path) -> np.ndarray:
    with Image.open(path) as img:
        return np.array(img)
```

- [ ] **Step 4: Write the step recorder**

`terrain/debug.py`:
```python
"""StepRecorder: writes one image per sub-step and a walkthrough document."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from terrain.imageio import save_gray8, to_uint8


@dataclass
class StepRecord:
    step_id: str
    title: str
    filename: str | None
    description: str
    params: dict = field(default_factory=dict)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


class StepRecorder:
    def __init__(self, out_dir: str | Path | None, enabled: bool):
        self.enabled = bool(enabled) and out_dir is not None
        self.out_dir = Path(out_dir) if out_dir is not None else None
        self.records: list[StepRecord] = []
        if self.enabled:
            (self.out_dir / "steps").mkdir(parents=True, exist_ok=True)

    def step(self, step_id: str, title: str, array: np.ndarray, description: str, params: dict | None = None) -> None:
        if not self.enabled:
            return
        filename = f"steps/{step_id}_{_slug(title)}.png"
        save_gray8(self.out_dir / filename, to_uint8(np.asarray(array)))
        self.records.append(StepRecord(step_id, title, filename, description, dict(params or {})))

    def note(self, step_id: str, title: str, description: str, params: dict | None = None) -> None:
        if not self.enabled:
            return
        self.records.append(StepRecord(step_id, title, None, description, dict(params or {})))

    def write_walkthrough(self) -> Path | None:
        if not self.enabled:
            return None
        lines = [
            "# Walkthrough",
            "",
            "This document shows each step of the generator.",
            "Each step shows the image it makes and the parameters that control it.",
            "",
        ]
        for r in self.records:
            lines += [f"## Step {r.step_id}: {r.title}", "", r.description, ""]
            if r.params:
                lines += ["| Parameter | Value |", "|---|---|"]
                lines += [f"| {k} | {v} |" for k, v in r.params.items()]
                lines.append("")
            if r.filename:
                lines += [f"![Step {r.step_id}]({r.filename})", ""]
        path = self.out_dir / "walkthrough.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        return path
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_debug.py -v`
Expected: 4 PASS

- [ ] **Step 6: Commit**

```bash
git add terrain/imageio.py terrain/debug.py tests/test_debug.py
git commit -m "Add image I/O and the step recorder"
```

---

### Task 4: Stage 1, circle

**Files:**
- Create: `terrain/circle.py`
- Test: `tests/test_circle.py`

**Interfaces:**
- Consumes: `CircleConfig`, `StepRecorder`, `smoothstep`.
- Produces: `CircleResult(mask: bool array, edge_band: float32, center_distance: float32, radius: float)`, `make_circle(size, cfg, recorder) -> CircleResult`.

- [ ] **Step 1: Write the failing tests**

`tests/test_circle.py`:
```python
import numpy as np

from terrain.circle import make_circle
from terrain.config import CircleConfig
from terrain.debug import StepRecorder


def test_mask_width_matches_diameter():
    size = 253
    cfg = CircleConfig(diameter_pct=90.0, edge_band_pct=10.0)
    res = make_circle(size, cfg, StepRecorder(None, False))
    row = res.mask[size // 2]
    width = int(row.sum())
    assert abs(width - size * 0.9) <= 1
    assert res.mask.dtype == np.bool_
    assert res.mask.shape == (size, size)


def test_edge_band_is_one_inside_and_zero_at_edge():
    size = 253
    res = make_circle(size, CircleConfig(diameter_pct=90.0, edge_band_pct=10.0), StepRecorder(None, False))
    c = size // 2
    assert res.edge_band[c, c] == 1.0
    assert res.edge_band[c, 0] == 0.0
    inner = int(res.radius * 0.85)
    assert res.edge_band[c, c + inner] == 1.0
    assert 0.0 < res.edge_band[c, c + int(res.radius * 0.96)] < 1.0


def test_records_three_steps(tmp_path):
    rec = StepRecorder(tmp_path, True)
    make_circle(127, CircleConfig(), rec)
    assert [r.step_id for r in rec.records] == ["01a", "01b", "01c"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_circle.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the circle module**

`terrain/circle.py`:
```python
"""Stage 1: the circular world mask."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from terrain.config import CircleConfig
from terrain.debug import StepRecorder
from terrain.noise import smoothstep


@dataclass
class CircleResult:
    mask: np.ndarray
    edge_band: np.ndarray
    center_distance: np.ndarray
    radius: float


def make_circle(size: int, cfg: CircleConfig, recorder: StepRecorder) -> CircleResult:
    center = (size - 1) / 2.0
    radius = size * cfg.diameter_pct / 200.0
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    distance = np.hypot(xx - center, yy - center).astype(np.float32)
    recorder.step(
        "01a", "Center distance", distance,
        "The generator computes the distance of each pixel from the image center. "
        "Black is the center. White is the corner.",
        {"size": size},
    )

    mask = distance <= radius
    recorder.step(
        "01b", "Circle mask", mask,
        "Pixels with a distance less than or equal to the radius are white. "
        "The radius is size * diameter_pct / 200.",
        {"diameter_pct": cfg.diameter_pct, "radius_px": round(radius, 1)},
    )

    inner = radius * (1.0 - cfg.edge_band_pct / 100.0)
    t = np.clip((radius - distance) / max(radius - inner, 1e-6), 0.0, 1.0)
    edge_band = smoothstep(t).astype(np.float32)
    edge_band[~mask] = 0.0
    recorder.step(
        "01c", "Edge band", edge_band,
        "A soft band inside the circle edge. The value is 1 inside the band start and 0 at the edge. "
        "The seabed uses this band to reach its floor at the edge.",
        {"edge_band_pct": cfg.edge_band_pct, "band_start_px": round(inner, 1)},
    )
    return CircleResult(mask=mask, edge_band=edge_band, center_distance=distance, radius=radius)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_circle.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add terrain/circle.py tests/test_circle.py
git commit -m "Add stage 1: circle mask"
```

---

### Task 5: Stage 2, landmasses

**Files:**
- Create: `terrain/landmass.py`
- Test: `tests/test_landmass.py`

**Interfaces:**
- Consumes: `CircleResult`, `LandmassConfig`, `GenerationError`, `fractal_noise`, `StepRecorder`.
- Produces: `LandResult(land_mask: bool array, landmass_ids: int32 array, seeds: list[tuple[float, float]], seed_used: int)`, `make_landmasses(circle, cfg, seed, recorder) -> LandResult`, `draw_dots(shape, points, radius, values=None) -> float32 array`.

- [ ] **Step 1: Write the failing tests**

`tests/test_landmass.py`:
```python
import numpy as np
import pytest
from scipy import ndimage

from terrain.circle import make_circle
from terrain.config import CircleConfig, GenerationError, LandmassConfig
from terrain.debug import StepRecorder
from terrain.landmass import make_landmasses

SIZE = 253


def _land(seed=42, **kw):
    circle = make_circle(SIZE, CircleConfig(), StepRecorder(None, False))
    cfg = LandmassConfig(**kw)
    return circle, make_landmasses(circle, cfg, seed, StepRecorder(None, False))


def test_exactly_three_landmasses():
    circle, res = _land()
    _, n = ndimage.label(res.land_mask)
    assert n == 3
    assert sorted(np.unique(res.landmass_ids).tolist()) == [0, 1, 2, 3]


def test_all_land_inside_circle():
    circle, res = _land()
    assert not (res.land_mask & ~circle.mask).any()


def test_ids_ordered_by_area():
    _, res = _land()
    areas = [int((res.landmass_ids == i).sum()) for i in (1, 2, 3)]
    assert areas == sorted(areas, reverse=True)


def test_no_small_lakes():
    _, res = _land(min_lake_area_px=200)
    sea_labels, n = ndimage.label(~res.land_mask)
    sizes = ndimage.sum(~res.land_mask, sea_labels, range(1, n + 1))
    assert all(s >= 200 for s in sizes)


def test_impossible_config_raises():
    with pytest.raises(GenerationError, match="landmasses after 2 tries"):
        _land(threshold=5.0, max_retries=2)


def test_deterministic():
    _, a = _land(seed=7)
    _, b = _land(seed=7)
    assert np.array_equal(a.landmass_ids, b.landmass_ids)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_landmass.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the landmass module**

`terrain/landmass.py`:
```python
"""Stage 2: three landmasses inside the circle."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from terrain.circle import CircleResult
from terrain.config import GenerationError, LandmassConfig
from terrain.debug import StepRecorder
from terrain.noise import fractal_noise

STAGE = 2


@dataclass
class LandResult:
    land_mask: np.ndarray
    landmass_ids: np.ndarray
    seeds: list[tuple[float, float]]
    seed_used: int


def draw_dots(shape, points, radius: float, values=None) -> np.ndarray:
    """White (or valued) discs on black, for the debug images."""
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]].astype(np.float32)
    out = np.zeros(shape, dtype=np.float32)
    for i, (x, y) in enumerate(points):
        v = 1.0 if values is None else float(values[i])
        out[np.hypot(xx - x, yy - y) <= radius] = v
    return out


def _place_seeds(rng, count, area_radius, separation, cx, cy):
    seeds: list[tuple[float, float]] = []
    rejections = 0
    while len(seeds) < count:
        r = area_radius * np.sqrt(rng.random())
        a = rng.random() * 2.0 * np.pi
        p = (cx + r * np.cos(a), cy + r * np.sin(a))
        if all(np.hypot(p[0] - q[0], p[1] - q[1]) >= separation for q in seeds):
            seeds.append((float(p[0]), float(p[1])))
        else:
            rejections += 1
            if rejections >= 1000:
                separation /= 2.0
                rejections = 0
    return seeds


def _keep_components(mask: np.ndarray, keep: int, min_area: int) -> np.ndarray:
    labels, n = ndimage.label(mask)
    if n == 0:
        return np.zeros_like(mask)
    sizes = np.asarray(ndimage.sum(mask, labels, range(1, n + 1)))
    order = np.argsort(sizes)[::-1]
    chosen = [int(i) + 1 for i in order[:keep] if sizes[i] >= min_area]
    return np.isin(labels, chosen)


def _fill_lakes(land: np.ndarray, min_area: int) -> np.ndarray:
    sea = ~land
    labels, n = ndimage.label(sea)
    if n == 0:
        return land
    sizes = np.asarray(ndimage.sum(sea, labels, range(1, n + 1)))
    small = [int(i) + 1 for i, s in enumerate(sizes) if s < min_area]
    return land | np.isin(labels, small)


def _label_by_area(land: np.ndarray) -> tuple[np.ndarray, int]:
    labels, n = ndimage.label(land)
    ids = np.zeros(land.shape, dtype=np.int32)
    if n == 0:
        return ids, 0
    sizes = np.asarray(ndimage.sum(land, labels, range(1, n + 1)))
    for rank, i in enumerate(np.argsort(sizes)[::-1]):
        ids[labels == int(i) + 1] = rank + 1
    return ids, n


def _attempt(circle: CircleResult, cfg: LandmassConfig, rng, recorder: StepRecorder, attempt: int):
    size = circle.mask.shape[0]
    center = (size - 1) / 2.0
    radius = circle.radius
    tag = "" if attempt == 0 else f"-try{attempt + 1}"

    seeds = _place_seeds(
        rng, cfg.count, radius * cfg.seed_area_pct / 100.0,
        radius * cfg.min_separation_pct / 100.0, center, center,
    )
    recorder.step(
        f"02a{tag}", "Seed points", draw_dots(circle.mask.shape, seeds, 4.0),
        "The generator places 3 seed points inside the circle. Each seed point is the center of one landmass. "
        "Rejection sampling keeps a minimum distance between the points.",
        {"seed_area_pct": cfg.seed_area_pct, "min_separation_pct": cfg.min_separation_pct,
         "seeds": [(round(x), round(y)) for x, y in seeds]},
    )

    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    falloff = np.zeros((size, size), dtype=np.float32)
    radii = []
    for sx, sy in seeds:
        r = rng.uniform(cfg.radius_pct[0], cfg.radius_pct[1]) / 100.0 * radius
        radii.append(round(r, 1))
        d = np.hypot(xx - sx, yy - sy)
        falloff = np.maximum(falloff, np.clip(1.0 - d / r, 0.0, 1.0))
    recorder.step(
        f"02b{tag}", "Radial falloff", falloff,
        "Each seed point gets a radial falloff: 1 at the seed point, 0 at the landmass radius. "
        "The image shows the maximum of the 3 fields.",
        {"radius_pct": list(cfg.radius_pct), "radii_px": radii},
    )

    noise = fractal_noise(
        (size, size), cfg.noise.octaves, cfg.noise.frequency,
        cfg.noise.lacunarity, cfg.noise.persistence, rng,
    )
    recorder.step(
        f"02c{tag}", "Noise", noise,
        "Fractal noise with several octaves. The noise makes the coast irregular.",
        {"octaves": cfg.noise.octaves, "frequency": cfg.noise.frequency,
         "lacunarity": cfg.noise.lacunarity, "persistence": cfg.noise.persistence},
    )

    field = falloff + cfg.noise_strength * (noise - 0.5)
    raw_land = (field > cfg.threshold) & circle.mask
    recorder.step(
        f"02d{tag}", "Land field", np.clip(field, 0.0, 1.0),
        "field = falloff + noise_strength * (noise - 0.5). "
        "Pixels with field > threshold inside the circle are land.",
        {"noise_strength": cfg.noise_strength, "threshold": cfg.threshold},
    )

    land = _keep_components(raw_land, cfg.count, cfg.min_lake_area_px)
    land = _fill_lakes(land, cfg.min_lake_area_px)
    recorder.step(
        f"02e{tag}", "Land mask", land,
        "The generator keeps the 3 largest connected areas. It removes islands and fills lakes "
        "smaller than min_lake_area_px.",
        {"min_lake_area_px": cfg.min_lake_area_px},
    )

    ids, count = _label_by_area(land)
    recorder.step(
        f"02f{tag}", "Landmass IDs", ids,
        "Each landmass gets an ID from 1 to 3. The largest landmass is 1. Sea is 0.",
        {"count": count, "areas_px": [int((ids == i).sum()) for i in range(1, count + 1)]},
    )
    return LandResult(land_mask=land, landmass_ids=ids, seeds=seeds, seed_used=0), count


def make_landmasses(circle: CircleResult, cfg: LandmassConfig, seed: int, recorder: StepRecorder) -> LandResult:
    count = 0
    for attempt in range(cfg.max_retries):
        rng = np.random.default_rng([seed, STAGE, attempt])
        result, count = _attempt(circle, cfg, rng, recorder, attempt)
        if count == cfg.count:
            result.seed_used = seed + attempt
            return result
        recorder.note(
            f"02-retry-{attempt}", "Retry",
            f"Try {attempt + 1} gave {count} landmasses, not {cfg.count}. The stage tries again with the next seed.",
            {"seed": seed + attempt, "count": count},
        )
    raise GenerationError(
        f"Seed {seed} gave {count} landmasses after {cfg.max_retries} tries. "
        "Increase landmass.radius_pct or decrease landmass.noise_strength."
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_landmass.py -v`
Expected: 6 PASS. If `test_exactly_three_landmasses` fails because a seed merged two landmasses, the retry loop must handle it; check that `max_retries` is 10 and the noise defaults match Task 1.

- [ ] **Step 5: Commit**

```bash
git add terrain/landmass.py tests/test_landmass.py
git commit -m "Add stage 2: three landmasses"
```

---

### Task 6: Stage 3, biome regions

**Files:**
- Create: `terrain/biomes.py`
- Test: `tests/test_biomes.py`

**Interfaces:**
- Consumes: `LandResult`, `BiomesConfig`, `BiomeType`, `GenerationError`, `fractal_noise`, `draw_dots`, `StepRecorder`.
- Produces: `Region(id, landmass_id, seed_xy, biome_index, subtype_index)`, `BiomeResult(coast_distance: float32, regions: list[Region], region_ids: int32, biome_ids: int32, subtype_ids: int32, seed_used: int)`, `make_biomes(land, cfg, seed, recorder) -> BiomeResult`, `subtype_id(biome_index, subtype_index) -> int`.

- [ ] **Step 1: Write the failing tests**

`tests/test_biomes.py`:
```python
import numpy as np

from terrain.biomes import make_biomes, subtype_id
from terrain.circle import make_circle
from terrain.config import BiomesConfig, CircleConfig, LandmassConfig
from terrain.debug import StepRecorder
from terrain.landmass import make_landmasses

SIZE = 253


def _world(seed=42):
    rec = StepRecorder(None, False)
    circle = make_circle(SIZE, CircleConfig(), rec)
    land = make_landmasses(circle, LandmassConfig(), seed, rec)
    cfg = BiomesConfig()
    return land, cfg, make_biomes(land, cfg, seed, rec)


def test_subtype_id_formula():
    assert subtype_id(0, 0) == 1
    assert subtype_id(0, 2) == 3
    assert subtype_id(4, 2) == 15


def test_every_biome_on_every_landmass():
    land, cfg, res = _world()
    for lm in (1, 2, 3):
        present = set(np.unique(res.biome_ids[land.landmass_ids == lm]).tolist())
        assert present == {1, 2, 3, 4, 5}


def test_every_subtype_appears():
    _, _, res = _world()
    assert set(np.unique(res.subtype_ids).tolist()) == set(range(16))


def test_region_ids_zero_exactly_on_sea():
    land, _, res = _world()
    assert np.array_equal(res.region_ids == 0, ~land.land_mask)
    assert np.array_equal(res.biome_ids == 0, ~land.land_mask)


def test_coast_regions_touch_coast_band():
    _, cfg, res = _world()
    coast_types = {i for i, t in enumerate(cfg.types) if t.placement == "coast"}
    for r in res.regions:
        if r.biome_index in coast_types:
            pix = res.region_ids == r.id
            assert res.coast_distance[pix].min() <= cfg.coast_band_px


def test_regions_stay_on_their_landmass():
    land, _, res = _world()
    for r in res.regions:
        pix = res.region_ids == r.id
        assert pix.any()
        assert set(np.unique(land.landmass_ids[pix]).tolist()) == {r.landmass_id}


def test_deterministic():
    _, _, a = _world(3)
    _, _, b = _world(3)
    assert np.array_equal(a.subtype_ids, b.subtype_ids)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_biomes.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the biomes module**

`terrain/biomes.py`:
```python
"""Stage 3: biome regions with sub-types."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from terrain.config import SUBTYPE_LETTERS, BiomesConfig, GenerationError
from terrain.debug import StepRecorder
from terrain.landmass import LandResult, draw_dots
from terrain.noise import fractal_noise

STAGE = 3
N_SUBTYPES = len(SUBTYPE_LETTERS)


@dataclass
class Region:
    id: int
    landmass_id: int
    seed_xy: tuple[float, float]
    biome_index: int
    subtype_index: int = 0


@dataclass
class BiomeResult:
    coast_distance: np.ndarray
    regions: list[Region]
    region_ids: np.ndarray
    biome_ids: np.ndarray
    subtype_ids: np.ndarray
    seed_used: int


def subtype_id(biome_index: int, subtype_index: int) -> int:
    return biome_index * N_SUBTYPES + subtype_index + 1


def _candidates(mask_lm: np.ndarray, coast: np.ndarray, placement: str, cfg: BiomesConfig):
    band = cfg.coast_band_px
    if placement == "coast":
        sel = mask_lm & (coast > 0) & (coast <= band)
    elif placement == "low":
        sel = mask_lm & (coast > band) & (coast <= 2.0 * band)
    elif placement == "inland":
        sel = mask_lm & (coast >= cfg.inland_fraction * float(coast[mask_lm].max()))
    else:
        sel = mask_lm & (coast > 10.0)
    if not sel.any():
        sel = mask_lm & (coast > 10.0)
    if not sel.any():
        sel = mask_lm
    return np.nonzero(sel)


def _place_region_seeds(land: LandResult, coast: np.ndarray, cfg: BiomesConfig, rng) -> list[Region]:
    regions: list[Region] = []
    n_types = len(cfg.types)
    lo, hi = cfg.seeds_per_landmass
    n_landmasses = int(land.landmass_ids.max())
    for lm in range(1, n_landmasses + 1):
        mask_lm = land.landmass_ids == lm
        n = int(rng.integers(lo, hi + 1))
        types = list(range(n_types)) + [int(v) for v in rng.integers(0, n_types, size=n - n_types)]
        placed: list[tuple[float, float]] = []
        separation = cfg.min_seed_separation_px
        rejections = 0
        for t in types:
            ys, xs = _candidates(mask_lm, coast, cfg.types[t].placement, cfg)
            while True:
                k = int(rng.integers(0, len(ys)))
                p = (float(xs[k]), float(ys[k]))
                if all(np.hypot(p[0] - q[0], p[1] - q[1]) >= separation for q in placed):
                    break
                rejections += 1
                if rejections >= 200:
                    separation /= 2.0
                    rejections = 0
            placed.append(p)
            regions.append(Region(id=len(regions) + 1, landmass_id=lm, seed_xy=p, biome_index=t))
    return regions


def _grow_regions(land: LandResult, regions: list[Region], dx: np.ndarray, dy: np.ndarray) -> np.ndarray:
    size = land.land_mask.shape[0]
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    px = xx + dx
    py = yy + dy
    region_ids = np.zeros((size, size), dtype=np.int32)
    for lm in range(1, int(land.landmass_ids.max()) + 1):
        rs = [r for r in regions if r.landmass_id == lm]
        ys, xs = np.nonzero(land.landmass_ids == lm)
        wx, wy = px[ys, xs], py[ys, xs]
        dist = np.stack([np.hypot(wx - r.seed_xy[0], wy - r.seed_xy[1]) for r in rs])
        best = np.argmin(dist, axis=0)
        region_ids[ys, xs] = np.array([r.id for r in rs], dtype=np.int32)[best]
    return region_ids


def _validate(regions, region_ids, coast, cfg) -> str | None:
    for r in regions:
        pix = region_ids == r.id
        if not pix.any():
            return f"region {r.id} has no pixels"
        if cfg.types[r.biome_index].placement == "coast" and float(coast[pix].min()) > cfg.coast_band_px:
            return f"coast region {r.id} does not touch the coast band"
    return None


def _assign_subtypes(regions: list[Region], n_types: int) -> None:
    for t in range(n_types):
        for i, r in enumerate(sorted((r for r in regions if r.biome_index == t), key=lambda r: r.id)):
            r.subtype_index = i % N_SUBTYPES


def _attempt(land, coast, cfg, rng, recorder, attempt):
    size = land.land_mask.shape[0]
    tag = "" if attempt == 0 else f"-try{attempt + 1}"
    n_types = len(cfg.types)

    regions = _place_region_seeds(land, coast, cfg, rng)
    recorder.step(
        f"03b{tag}", "Region seeds",
        draw_dots(land.land_mask.shape, [r.seed_xy for r in regions], 4.0,
                  [(r.biome_index + 1) / n_types for r in regions]),
        "The generator scatters region seeds on each landmass. The first 5 seeds on each landmass get one "
        "biome type each, so every landmass has every biome type. Extra seeds get a random biome type. "
        "Each seed obeys the placement rule of its biome type: coast, low, inland, or any. "
        "Brighter dots are later biome types in the list.",
        {"seeds_per_landmass": list(cfg.seeds_per_landmass), "min_seed_separation_px": cfg.min_seed_separation_px,
         "coast_band_px": cfg.coast_band_px, "inland_fraction": cfg.inland_fraction,
         "regions": len(regions),
         "placement": {t.name: t.placement for t in cfg.types}},
    )

    warp = cfg.warp
    dx = warp.strength_px * (fractal_noise((size, size), warp.octaves, warp.frequency, 2.0, 0.5, rng) - 0.5) * 2.0
    dy = warp.strength_px * (fractal_noise((size, size), warp.octaves, warp.frequency, 2.0, 0.5, rng) - 0.5) * 2.0
    recorder.step(
        f"03c{tag}", "Warp noise", dx,
        "Two noise fields give each pixel an offset (dx, dy). The offset bends the region borders, "
        "so they are organic and not straight. The image shows dx.",
        {"strength_px": warp.strength_px, "frequency": warp.frequency, "octaves": warp.octaves},
    )

    region_ids = _grow_regions(land, regions, dx, dy)
    recorder.step(
        f"03d{tag}", "Region IDs", region_ids,
        "Each land pixel goes to the nearest seed on the same landmass. The generator measures the distance "
        "from the warped pixel position, pixel + offset, to the seed.",
        {"regions": len(regions)},
    )

    problem = _validate(regions, region_ids, coast, cfg)
    if problem is not None:
        return None, problem

    _assign_subtypes(regions, n_types)
    biome_lut = np.zeros(len(regions) + 1, dtype=np.int32)
    subtype_lut = np.zeros(len(regions) + 1, dtype=np.int32)
    for r in regions:
        biome_lut[r.id] = r.biome_index + 1
        subtype_lut[r.id] = subtype_id(r.biome_index, r.subtype_index)
    biome_ids = biome_lut[region_ids]
    subtype_ids = subtype_lut[region_ids]

    recorder.step(
        f"03e{tag}", "Biome IDs", biome_ids,
        "Each region maps to its biome type. The image has 6 gray levels: sea plus 5 biome types.",
        {"biomes": {i + 1: t.label for i, t in enumerate(cfg.types)}},
    )
    recorder.step(
        f"03f{tag}", "Sub-type IDs", subtype_ids,
        "Each region gets a sub-type A, B, or C. For each biome type, the generator cycles A, B, C over its "
        "regions in ID order, so every sub-type appears. The image has 16 gray levels: sea plus 15 sub-types.",
        {"subtype_ids": {subtype_id(r.biome_index, r.subtype_index):
                         f"{cfg.types[r.biome_index].name} {SUBTYPE_LETTERS[r.subtype_index]}"
                         for r in sorted(regions, key=lambda r: subtype_id(r.biome_index, r.subtype_index))}},
    )
    for i, t in enumerate(cfg.types):
        recorder.step(
            f"03g-{i + 1}", f"Mask {t.name}", biome_ids == i + 1,
            f"White where the biome type is {t.label}.",
        )
    return BiomeResult(coast, regions, region_ids, biome_ids, subtype_ids, 0), None


def make_biomes(land: LandResult, cfg: BiomesConfig, seed: int, recorder: StepRecorder) -> BiomeResult:
    coast = ndimage.distance_transform_edt(land.land_mask).astype(np.float32)
    recorder.step(
        "03a", "Coast distance", coast,
        "The distance from each land pixel to the nearest sea pixel. Sea is 0. "
        "The placement rules and the heightmap use this distance.",
        {"max_px": round(float(coast.max()), 1)},
    )
    problem = ""
    for attempt in range(cfg.max_retries):
        rng = np.random.default_rng([seed, STAGE, attempt])
        result, problem = _attempt(land, coast, cfg, rng, recorder, attempt)
        if result is not None:
            result.seed_used = seed + attempt
            return result
        recorder.note(
            f"03-retry-{attempt}", "Retry",
            f"Try {attempt + 1} failed: {problem}. The stage tries again with the next seed.",
            {"seed": seed + attempt},
        )
    raise GenerationError(
        f"Seed {seed} could not place biome regions after {cfg.max_retries} tries: {problem}. "
        "Decrease biomes.warp.strength_px or biomes.min_seed_separation_px."
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_biomes.py -v`
Expected: 7 PASS

- [ ] **Step 5: Commit**

```bash
git add terrain/biomes.py tests/test_biomes.py
git commit -m "Add stage 3: biome regions and sub-types"
```

---

### Task 7: Stage 4, heightmap

**Files:**
- Create: `terrain/heightmap.py`
- Test: `tests/test_heightmap.py`

**Interfaces:**
- Consumes: `CircleResult`, `LandResult`, `BiomeResult`, `HeightmapConfig`, `Profile`, `fractal_noise`, `ridged_noise`, `smoothstep`, `StepRecorder`.
- Produces: `HeightResult(height: float32)`, `make_heightmap(circle, land, biomes, cfg, seed, recorder) -> HeightResult`, `biome_weights(biome_ids, n_types, blur_px) -> float32 (n_types, H, W)`.

- [ ] **Step 1: Write the failing tests**

`tests/test_heightmap.py`:
```python
import numpy as np

from terrain.biomes import make_biomes
from terrain.circle import make_circle
from terrain.config import BiomesConfig, CircleConfig, HeightmapConfig, LandmassConfig
from terrain.debug import StepRecorder
from terrain.heightmap import biome_weights, make_heightmap
from terrain.landmass import make_landmasses

SIZE = 253


def _world(seed=42):
    rec = StepRecorder(None, False)
    circle = make_circle(SIZE, CircleConfig(), rec)
    land = make_landmasses(circle, LandmassConfig(), seed, rec)
    biomes = make_biomes(land, BiomesConfig(), seed, rec)
    cfg = HeightmapConfig()
    return circle, land, biomes, cfg, make_heightmap(circle, land, biomes, cfg, seed, rec)


def test_ranges():
    circle, land, biomes, cfg, res = _world()
    h = res.height
    assert h.dtype == np.float32
    assert h[land.land_mask].min() >= 0.0 and h[land.land_mask].max() <= 1.0
    sea = h[~land.land_mask]
    assert sea.max() <= 0.0 and sea.min() >= -cfg.seabed_depth - 1e-6


def test_coast_is_near_zero_and_outside_is_floor():
    circle, land, biomes, cfg, res = _world()
    coast = land.land_mask & (biomes.coast_distance <= 1.5)
    assert res.height[coast].max() < 0.02
    assert np.allclose(res.height[~circle.mask], -cfg.seabed_depth)


def test_mountains_higher_than_marsh():
    circle, land, biomes, cfg, res = _world()
    mountain = res.height[biomes.biome_ids == 5].mean()
    marsh = res.height[biomes.biome_ids == 2].mean()
    assert mountain > marsh


def test_biome_weights_sum_to_one_on_land():
    ids = np.zeros((32, 32), dtype=np.int32)
    ids[4:28, 4:16] = 1
    ids[4:28, 16:28] = 2
    w = biome_weights(ids, 2, 3.0)
    assert w.shape == (2, 32, 32)
    assert np.allclose(w.sum(0)[ids > 0], 1.0)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_heightmap.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the heightmap module**

`terrain/heightmap.py`:
```python
"""Stage 4: the heightmap."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from terrain.biomes import BiomeResult
from terrain.circle import CircleResult
from terrain.config import HeightmapConfig
from terrain.debug import StepRecorder
from terrain.landmass import LandResult
from terrain.noise import fractal_noise, ridged_noise, smoothstep

STAGE = 4


@dataclass
class HeightResult:
    height: np.ndarray


def biome_weights(biome_ids: np.ndarray, n_types: int, blur_px: float) -> np.ndarray:
    """Blurred one-hot masks, normalized to sum 1 where the sum is positive."""
    onehot = np.stack([(biome_ids == i + 1) for i in range(n_types)]).astype(np.float32)
    blurred = ndimage.gaussian_filter(onehot, sigma=(0.0, blur_px, blur_px))
    total = blurred.sum(axis=0, keepdims=True)
    return (blurred / np.maximum(total, 1e-6)).astype(np.float32)


def make_heightmap(circle: CircleResult, land: LandResult, biomes: BiomeResult,
                   cfg: HeightmapConfig, seed: int, recorder: StepRecorder) -> HeightResult:
    size = land.land_mask.shape[0]
    land_mask = land.land_mask
    names = list(cfg.profiles)
    n_types = int(biomes.biome_ids.max())

    sea_distance = ndimage.distance_transform_edt(~land_mask).astype(np.float32)
    signed = np.where(land_mask, biomes.coast_distance, -sea_distance).astype(np.float32)
    recorder.step(
        "04a", "Signed coast distance", signed,
        "The distance to the coast. Land is positive. Sea is negative. The coast is 0.",
        {"max_land_px": round(float(signed.max()), 1), "max_sea_px": round(float(-signed.min()), 1)},
    )

    curve = smoothstep(np.clip(signed / cfg.coast_distance_px, 0.0, 1.0)).astype(np.float32)
    curve[~land_mask] = 0.0
    recorder.step(
        "04b", "Coast curve", curve,
        "A smooth curve from 0 at the coast to 1 at coast_distance_px inland. "
        "The curve keeps the coast at sea level.",
        {"coast_distance_px": cfg.coast_distance_px},
    )

    weights = biome_weights(biomes.biome_ids, n_types, cfg.profile_blur_px)
    base_map = np.zeros((size, size), dtype=np.float32)
    amp_map = np.zeros((size, size), dtype=np.float32)
    noise_map = np.zeros((size, size), dtype=np.float32)
    for i in range(n_types):
        p = cfg.profiles[names[i]]
        base_map += weights[i] * p.base
        amp_map += weights[i] * p.amplitude
        rng = np.random.default_rng([seed, STAGE, i])
        gen = ridged_noise if p.ridged else fractal_noise
        noise_map += weights[i] * gen((size, size), p.octaves, p.frequency, 2.0, 0.5, rng)
    recorder.step(
        "04c", "Profile base", base_map,
        "Each biome type has a height profile with a base height and a noise amplitude. The generator blurs "
        "the biome masks with profile_blur_px and mixes the profiles, so the height changes smoothly at "
        "biome borders. This image is the base height.",
        {"profile_blur_px": cfg.profile_blur_px,
         "base": {n: cfg.profiles[n].base for n in names}},
    )
    recorder.step(
        "04c-2", "Profile amplitude", amp_map,
        "The mixed noise amplitude of the biome profiles.",
        {"amplitude": {n: cfg.profiles[n].amplitude for n in names}},
    )
    recorder.step(
        "04d", "Biome noise", noise_map,
        "One noise field per biome type, mixed with the same weights. Mountain Range uses ridged noise "
        "for sharp crests. The other biomes use fractal noise.",
        {n: f"frequency {cfg.profiles[n].frequency}, octaves {cfg.profiles[n].octaves}, ridged {cfg.profiles[n].ridged}"
         for n in names},
    )

    land_height = np.clip(curve * (base_map + amp_map * (2.0 * noise_map - 1.0)), 0.0, 1.0).astype(np.float32)
    recorder.step(
        "04e", "Land height", land_height,
        "land = clamp(curve * (base + amplitude * (2 * noise - 1)), 0, 1). "
        "The curve multiplies the whole sum, so the coast stays at 0.",
    )

    depth = cfg.seabed_depth
    seabed = -depth * smoothstep(np.clip(-signed / cfg.seabed_distance_px, 0.0, 1.0))
    seabed = seabed * circle.edge_band + (-depth) * (1.0 - circle.edge_band)
    seabed = seabed.astype(np.float32)
    recorder.step(
        "04f", "Seabed", seabed,
        "The seabed goes down from 0 at the coast to the floor at seabed_distance_px. "
        "The edge band blends the seabed to the floor at the circle edge and outside the circle.",
        {"seabed_depth": depth, "seabed_distance_px": cfg.seabed_distance_px},
    )

    height = np.where(land_mask, land_height, seabed).astype(np.float32)
    recorder.step(
        "04g", "Height", height,
        "The land height and the seabed together. The image maps the floor to black and the highest "
        "point to white. Sea level is a mid gray.",
        {"min": round(float(height.min()), 3), "max": round(float(height.max()), 3)},
    )
    return HeightResult(height=height)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_heightmap.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add terrain/heightmap.py tests/test_heightmap.py
git commit -m "Add stage 4: heightmap"
```

---

### Task 8: Stage 5, Unreal export and previews

**Files:**
- Create: `terrain/export.py`
- Test: `tests/test_export.py`

**Interfaces:**
- Consumes: `Config`, `LandResult`, `BiomeResult`, `HeightResult`, `config_to_dict`, `SUBTYPE_LETTERS`, `save_gray8`, `save_gray16`, `save_rgb`, `load_array`.
- Produces: `encode_height16(height, sea_level_value) -> uint16`, `largest_remainder_255(weights) -> uint8`, `make_weight_maps(biome_ids, land_mask, n_types, blur_px) -> uint8 (n_types, H, W)`, `unreal_import_settings(size, sea_level_value) -> dict`, `export_unreal(cfg, land, biomes, height, out_dir, seeds_used) -> list[Path]`, `write_previews(cfg, biomes, height, out_dir) -> list[Path]`.

- [ ] **Step 1: Write the failing tests**

`tests/test_export.py`:
```python
import json

import numpy as np

from terrain.biomes import make_biomes
from terrain.circle import make_circle
from terrain.config import Config, config_from_dict
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
    assert sorted(p.name for p in previews) == ["biomes_color.png", "height_shaded.png"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_export.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the export module**

`terrain/export.py`:
```python
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


def make_weight_maps(biome_ids: np.ndarray, land_mask: np.ndarray, n_types: int, blur_px: float) -> np.ndarray:
    idx = ndimage.distance_transform_edt(~land_mask, return_distances=False, return_indices=True)
    filled = biome_ids[idx[0], idx[1]]
    onehot = np.stack([(filled == i + 1) for i in range(n_types)]).astype(np.float32)
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

    files.append(save_gray16(out / "heightmap.png", encode_height16(height.height, cfg.export.sea_level_value)))

    weights = make_weight_maps(biomes.biome_ids, land.land_mask, n_types, cfg.export.weight_blur_px)
    for i, t in enumerate(cfg.biomes.types):
        files.append(save_gray8(out / f"weight_{t.name}.png", weights[i]))

    for i, t in enumerate(cfg.biomes.types):
        for s, letter in enumerate(SUBTYPE_LETTERS):
            sid = i * len(SUBTYPE_LETTERS) + s + 1
            mask = np.where(biomes.subtype_ids == sid, 255, 0).astype(np.uint8)
            files.append(save_gray8(out / f"subtype_{t.name}_{letter}.png", mask))

    params = {
        "seed": cfg.seed,
        "seeds_used": seeds_used,
        "config": config_to_dict(cfg),
        "biome_ids": {i + 1: t.label for i, t in enumerate(cfg.biomes.types)},
        "subtype_ids": {i * len(SUBTYPE_LETTERS) + s + 1: f"{t.label} {letter}"
                        for i, t in enumerate(cfg.biomes.types) for s, letter in enumerate(SUBTYPE_LETTERS)},
        "regions": [{"id": r.id, "landmass": r.landmass_id, "biome": cfg.biomes.types[r.biome_index].name,
                     "subtype": SUBTYPE_LETTERS[r.subtype_index],
                     "seed_xy": [round(r.seed_xy[0]), round(r.seed_xy[1])]} for r in biomes.regions],
        "unreal_import": unreal_import_settings(cfg.size, cfg.export.sea_level_value),
    }
    path = out / "params.json"
    path.write_text(json.dumps(params, indent=2), encoding="utf-8")
    files.append(path)
    return files


def hillshade(height: np.ndarray, z_factor: float, azimuth_deg: float = 315.0, altitude_deg: float = 45.0) -> np.ndarray:
    dy, dx = np.gradient(height.astype(np.float64) * z_factor)
    zenith = np.radians(90.0 - altitude_deg)
    azimuth = np.radians(360.0 - azimuth_deg + 90.0)
    slope = np.arctan(np.hypot(dx, dy))
    aspect = np.arctan2(dy, -dx)
    shade = np.cos(zenith) * np.cos(slope) + np.sin(zenith) * np.sin(slope) * np.cos(azimuth - aspect)
    return np.clip(shade, 0.0, 1.0)


def write_previews(cfg: Config, biomes: BiomeResult, height: HeightResult, out_dir: str | Path) -> list[Path]:
    out = Path(out_dir)
    h = height.height
    size = h.shape[0]
    shade = hillshade(h, z_factor=size / 4.0)
    norm = (h - h.min()) / max(float(h.max() - h.min()), 1e-6)
    shaded = np.clip(0.65 * shade + 0.35 * norm, 0.0, 1.0)
    shaded[h < 0.0] *= 0.6
    files = [save_gray8(out / "height_shaded.png", np.round(shaded * 255.0).astype(np.uint8))]

    rgb = np.zeros((size, size, 3), dtype=np.float32)
    rgb[...] = SEA_COLOR
    n_sub = len(SUBTYPE_LETTERS)
    for i in range(len(cfg.biomes.types)):
        for s in range(n_sub):
            sid = i * n_sub + s + 1
            color = np.array(PALETTE[i % len(PALETTE)], dtype=np.float32) * SUBTYPE_LIGHTNESS[s]
            rgb[biomes.subtype_ids == sid] = np.clip(color, 0, 255)
    land = biomes.biome_ids > 0
    rgb[land] = rgb[land] * (0.6 + 0.4 * shade[land][:, None])
    files.append(save_rgb(out / "biomes_color.png", np.clip(rgb, 0, 255).astype(np.uint8)))
    return files
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_export.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add terrain/export.py tests/test_export.py
git commit -m "Add stage 5: Unreal export and previews"
```

---

### Task 9: Pipeline, CLI, and README

**Files:**
- Create: `terrain/pipeline.py`, `terrain/cli.py`, `terrain/__main__.py`, `README.md`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `PipelineResult(config, circle, land, biomes, height, files, walkthrough)`, `run_pipeline(cfg, out_dir, debug=False) -> PipelineResult`, `main(argv=None) -> int`.

- [ ] **Step 1: Write the failing tests**

`tests/test_pipeline.py`:
```python
import hashlib
from pathlib import Path

from terrain.cli import main
from terrain.config import config_from_dict
from terrain.pipeline import run_pipeline


def _digest(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def test_same_seed_same_bytes(tmp_path):
    cfg = config_from_dict({"size": 253, "seed": 11})
    run_pipeline(cfg, tmp_path / "a", debug=True)
    run_pipeline(cfg, tmp_path / "b", debug=True)
    a, b = _digest(tmp_path / "a"), _digest(tmp_path / "b")
    assert a == b
    assert len(a) > 40


def test_debug_writes_steps_and_walkthrough(tmp_path):
    cfg = config_from_dict({"size": 253})
    res = run_pipeline(cfg, tmp_path, debug=True)
    steps = list((tmp_path / "steps").glob("*.png"))
    assert len(steps) >= 20
    assert res.walkthrough == tmp_path / "walkthrough.md"
    text = res.walkthrough.read_text(encoding="utf-8")
    assert "## Step 01a" in text and "## Step 04g" in text


def test_no_debug_writes_no_steps(tmp_path):
    cfg = config_from_dict({"size": 253})
    res = run_pipeline(cfg, tmp_path, debug=False)
    assert not (tmp_path / "steps").exists()
    assert res.walkthrough is None
    assert (tmp_path / "unreal" / "heightmap.png").exists()


def test_cli_runs_and_rejects_bad_size(tmp_path, capsys):
    assert main(["--size", "253", "--seed", "3", "--out", str(tmp_path / "o")]) == 0
    assert (tmp_path / "o" / "unreal" / "heightmap.png").exists()
    assert main(["--size", "1000", "--out", str(tmp_path / "p")]) == 1
    assert "127, 253, 505" in capsys.readouterr().err
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the pipeline module**

`terrain/pipeline.py`:
```python
"""Runs the five stages in order."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from terrain.biomes import BiomeResult, make_biomes
from terrain.circle import CircleResult, make_circle
from terrain.config import Config
from terrain.debug import StepRecorder
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


def run_pipeline(cfg: Config, out_dir: str | Path, debug: bool = False) -> PipelineResult:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    recorder = StepRecorder(out, debug)
    circle = make_circle(cfg.size, cfg.circle, recorder)
    land = make_landmasses(circle, cfg.landmass, cfg.seed, recorder)
    biomes = make_biomes(land, cfg.biomes, cfg.seed, recorder)
    height = make_heightmap(circle, land, biomes, cfg.heightmap, cfg.seed, recorder)
    seeds_used = {"landmass": land.seed_used, "biomes": biomes.seed_used}
    files = export_unreal(cfg, land, biomes, height, out / "unreal", seeds_used)
    files += write_previews(cfg, biomes, height, out / "preview")
    walkthrough = recorder.write_walkthrough()
    return PipelineResult(cfg, circle, land, biomes, height, files, walkthrough)
```

- [ ] **Step 4: Write the CLI**

`terrain/cli.py`:
```python
"""Command line interface."""
from __future__ import annotations

import argparse
import sys
import time

from terrain.config import ConfigError, GenerationError, load_config
from terrain.pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="terrain", description="Generate a circular world for Unreal Engine.")
    p.add_argument("--config", help="YAML file with parameters")
    p.add_argument("--seed", type=int, help="random seed (default 42)")
    p.add_argument("--size", type=int, help="image width and height in pixels (default 1009)")
    p.add_argument("--diameter", type=float, help="circle diameter as a percentage of the width (default 90)")
    p.add_argument("--out", default="out", help="output folder (default out)")
    p.add_argument("--debug", action="store_true", help="write sub-step images and walkthrough.md")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    overrides: dict = {}
    if args.seed is not None:
        overrides["seed"] = args.seed
    if args.size is not None:
        overrides["size"] = args.size
    if args.diameter is not None:
        overrides["circle"] = {"diameter_pct": args.diameter}
    try:
        cfg = load_config(args.config, overrides)
        start = time.perf_counter()
        result = run_pipeline(cfg, args.out, debug=args.debug)
    except (ConfigError, GenerationError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    seconds = time.perf_counter() - start
    print(f"Wrote {len(result.files)} files to {args.out} in {seconds:.1f} s.")
    if result.walkthrough is not None:
        print(f"Walkthrough: {result.walkthrough}")
    return 0
```

`terrain/__main__.py`:
```python
import sys

from terrain.cli import main

sys.exit(main())
```

- [ ] **Step 5: Write the README**

`README.md`:
```markdown
# Terrain generator

The generator makes a circular world with 3 landmasses and 5 biome types for Unreal Engine.
All output images are grayscale PNG files.

## Install

```
pip install -r requirements.txt
```

## Run

```
python -m terrain --seed 42 --size 1009 --diameter 90 --out out --debug
```

| Flag | Meaning | Default |
|---|---|---|
| `--config PATH` | YAML file with parameters, see `config.yaml` | built-in defaults |
| `--seed INT` | random seed | 42 |
| `--size INT` | image size: 127, 253, 505, 1009, 2017, 4033, or 8129 | 1009 |
| `--diameter FLOAT` | circle diameter as a percentage of the width | 90 |
| `--out PATH` | output folder | `out` |
| `--debug` | write one image per sub-step and `walkthrough.md` | off |

## Output

- `out/unreal/heightmap.png`: 16-bit heightmap. Sea level is at value 32768.
- `out/unreal/weight_<biome>.png`: 5 layer weight maps. They add up to 255 at each pixel.
- `out/unreal/subtype_<biome>_<A|B|C>.png`: 15 sub-type masks.
- `out/unreal/params.json`: the seed, the parameters, and the Unreal import settings.
- `out/preview/`: a hill shade and a color biome map for people.
- `out/steps/` and `out/walkthrough.md`: one image per sub-step, with `--debug`.

## Import into Unreal

1. Open the Landscape mode and select Import from File.
2. Select `out/unreal/heightmap.png` as the heightmap file.
3. Set the section size to 63x63 quads and the sections per component to 2x2.
4. Set the component count to the value in `params.json`, for example 8x8 for 1009.
5. Set the Z scale to 100. Value 32768 is then 0 m, and 65535 is 256 m.
6. Add 5 layers in the landscape material, one per biome type.
7. Select each `weight_<biome>.png` as the layer file for its layer.

## Tests

```
python -m pytest
```
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add terrain/pipeline.py terrain/cli.py terrain/__main__.py README.md tests/test_pipeline.py
git commit -m "Add pipeline, CLI, and README"
```

---

### Task 10: Full-size run and visual check

**Files:**
- Modify: `terrain/config.py` and `config.yaml` (only if the defaults need a change)

- [ ] **Step 1: Generate the default world at 1009 with debug output**

Run: `python -m terrain --debug --out out`
Expected: exit code 0, a line `Wrote 23 files to out in N s.`, and `out/walkthrough.md`.

- [ ] **Step 2: Look at the previews and the step images**

Open `out/preview/biomes_color.png`, `out/preview/height_shaded.png`, and `out/steps/02e_land_mask.png`.
Check:
- The 3 landmasses are separate and have irregular coasts.
- The landmasses fill the circle without a flat cut along the circle edge on more than one side.
- Sea Side regions sit at the coast. Mountain Range regions sit inland.
- The hill shade shows mountains higher than the forests and the marsh flat.

- [ ] **Step 3: Tune the defaults if a check fails**

Change the default in both `terrain/config.py` and `config.yaml`. Run `python -m pytest` after each change.

- [ ] **Step 4: Commit**

```bash
git add terrain/config.py config.yaml
git commit -m "Tune default parameters after a full-size run"
```
