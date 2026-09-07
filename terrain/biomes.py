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
    type_names: list[str]
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
        same = sorted((r for r in regions if r.biome_index == t), key=lambda r: r.id)
        for i, r in enumerate(same):
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
        "The generator scatters region seeds on each landmass. The first 5 seeds on each landmass get "
        "one biome type each, so every landmass has every biome type. Extra seeds get a random biome "
        "type. Each seed obeys the placement rule of its biome type: coast, low, inland, or any. "
        "Brighter dots are later biome types in the list.",
        {"seeds_per_landmass": list(cfg.seeds_per_landmass),
         "min_seed_separation_px": cfg.min_seed_separation_px,
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
        "Each land pixel goes to the nearest seed on the same landmass. The generator measures the "
        "distance from the warped pixel position, pixel + offset, to the seed.",
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
    by_subtype = sorted(regions, key=lambda r: subtype_id(r.biome_index, r.subtype_index))
    recorder.step(
        f"03f{tag}", "Sub-type IDs", subtype_ids,
        "Each region gets a sub-type A, B, or C. For each biome type, the generator cycles A, B, C "
        "over its regions in ID order, so every sub-type appears. The image has 16 gray levels: sea "
        "plus 15 sub-types.",
        {"subtype_ids": {subtype_id(r.biome_index, r.subtype_index):
                         f"{cfg.types[r.biome_index].name} {SUBTYPE_LETTERS[r.subtype_index]}"
                         for r in by_subtype}},
    )
    for i, t in enumerate(cfg.types):
        recorder.step(
            f"03g-{i + 1}", f"Mask {t.name}", biome_ids == i + 1,
            f"White where the biome type is {t.label}.",
        )
    result = BiomeResult(coast, regions, region_ids, biome_ids, subtype_ids,
                         [t.name for t in cfg.types], 0)
    return result, None


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
