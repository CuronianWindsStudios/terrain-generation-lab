"""Stage 3: biome regions with sub-types."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from terrain.config import SUBTYPE_LETTERS, BiomesConfig, GenerationError
from terrain.debug import StepRecorder
from terrain.debug import draw_dots
from terrain.landmass import LandResult
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


def _seeded_types(cfg: BiomesConfig) -> list[int]:
    """The biome types that get region seeds. Spit types cover the spits and get no seeds."""
    return [i for i, t in enumerate(cfg.types) if t.placement != "spit"]


def _place_region_seeds(land: LandResult, coast: np.ndarray, cfg: BiomesConfig, rng) -> list[Region]:
    regions: list[Region] = []
    seeded = _seeded_types(cfg)
    lo, hi = cfg.seeds_per_landmass
    n_landmasses = int(land.landmass_ids.max())
    for lm in range(1, n_landmasses + 1):
        mask_lm = (land.landmass_ids == lm) & ~land.spit_mask
        n = int(rng.integers(lo, hi + 1))
        extra = rng.integers(0, len(seeded), size=max(n - len(seeded), 0))
        types = list(seeded) + [seeded[int(v)] for v in extra]
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


def _grow_regions(land: LandResult, regions: list[Region], dx: np.ndarray, dy: np.ndarray,
                  scale: dict[int, float] | None = None) -> np.ndarray:
    """Each mainland pixel goes to the nearest seed on its land. The scale multiplies the distance
    per region id, so a biome with a scale above 1 gives up pixels at its borders. A seed is always
    nearest to itself, so no region can lose all its pixels."""
    size = land.land_mask.shape[0]
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    px = xx + dx
    py = yy + dy
    region_ids = np.zeros((size, size), dtype=np.int32)
    for lm in range(1, int(land.landmass_ids.max()) + 1):
        rs = [r for r in regions if r.landmass_id == lm]
        ys, xs = np.nonzero((land.landmass_ids == lm) & ~land.spit_mask)
        wx, wy = px[ys, xs], py[ys, xs]
        dist = np.stack([np.hypot(wx - r.seed_xy[0], wy - r.seed_xy[1]) * (scale.get(r.id, 1.0) if scale else 1.0)
                         for r in rs])
        best = np.argmin(dist, axis=0)
        region_ids[ys, xs] = np.array([r.id for r in rs], dtype=np.int32)[best]
    return region_ids


def _balance_regions(land: LandResult, regions: list[Region], dx: np.ndarray, dy: np.ndarray,
                     cfg: BiomesConfig) -> tuple[np.ndarray, dict[int, float]]:
    """Tunes one distance scale per biome type and land until the seeded biome types share each
    land about equally. Returns the region ids and the scale per region id."""
    seeded = _seeded_types(cfg)
    target = 1.0 / max(len(seeded), 1)
    scale: dict[int, float] = {r.id: 1.0 for r in regions}
    region_ids = _grow_regions(land, regions, dx, dy, scale)
    for it in range(cfg.balance_iterations):
        # the step shrinks each round, so two neighbors cannot trade the same strip back and forth
        exponent = 0.35 * 0.8 ** it
        worst = 0.0
        for lm in range(1, int(land.landmass_ids.max()) + 1):
            mainland = (land.landmass_ids == lm) & ~land.spit_mask
            total = float(mainland.sum())
            if total == 0.0:
                continue
            for t in seeded:
                ids = [r.id for r in regions if r.landmass_id == lm and r.biome_index == t]
                if not ids:
                    continue
                share = float((mainland & np.isin(region_ids, ids)).sum()) / total
                worst = max(worst, abs(share - target))
                # a damped step: at most a third up or down per round, so the shares do not oscillate
                factor = float(np.clip((max(share, 1e-3) / target) ** exponent, 0.75, 1.33))
                for rid in ids:
                    scale[rid] = float(np.clip(scale[rid] * factor, 0.05, 20.0))
        if worst <= cfg.balance_tolerance:
            break
        region_ids = _grow_regions(land, regions, dx, dy, scale)
    return region_ids, scale


def _spit_regions(land: LandResult, regions: list[Region], region_ids: np.ndarray,
                  cfg: BiomesConfig) -> None:
    """One region per spit. The regions are appended to the list and drawn into region_ids."""
    spit_types = [i for i, t in enumerate(cfg.types) if t.placement == "spit"]
    if not spit_types:
        return
    biome_index = spit_types[0]
    yy, xx = np.mgrid[0:region_ids.shape[0], 0:region_ids.shape[1]]
    for lm in range(1, int(land.landmass_ids.max()) + 1):
        pix = land.spit_mask & (land.spit_owner == lm)
        if not pix.any():
            continue
        center = (float(xx[pix].mean()), float(yy[pix].mean()))
        region = Region(id=len(regions) + 1, landmass_id=lm, seed_xy=center, biome_index=biome_index)
        regions.append(region)
        region_ids[pix] = region.id


def _drop_empty_regions(regions: list[Region], region_ids: np.ndarray) -> list[Region]:
    """The balance can shrink an extra seed of a biome type to nothing. Such a region goes away,
    and the ids of the others stay dense. A region is kept when it has at least one pixel."""
    counts = np.bincount(region_ids.ravel(), minlength=len(regions) + 1)
    kept = [r for r in regions if counts[r.id] > 0]
    remap = np.zeros(len(regions) + 1, dtype=np.int32)
    for new_id, r in enumerate(kept, start=1):
        remap[r.id] = new_id
        r.id = new_id
    region_ids[...] = remap[region_ids]
    return kept


def _validate(regions, region_ids, coast, cfg) -> str | None:
    n_lands = max((r.landmass_id for r in regions), default=0)
    for lm in range(1, n_lands + 1):
        for t in range(len(cfg.types)):
            if cfg.types[t].placement == "spit":
                continue
            if not any(r.landmass_id == lm and r.biome_index == t for r in regions):
                return f"landmass {lm} lost every region of biome {cfg.types[t].name}"
    for r in regions:
        pix = region_ids == r.id
        if not pix.any():
            return f"region {r.id} has no pixels"
        if cfg.types[r.biome_index].placement == "coast" and float(coast[pix].min()) > cfg.coast_band_px:
            return f"coast region {r.id} does not touch the coast band"
    return None


def _assign_subtypes(regions: list[Region], n_types: int, n_landmasses: int, rng) -> dict[int, list[int]]:
    """Each landmass gets one sub-type of each biome type, and no two landmasses share it.

    For each biome type the generator draws a random order of A, B, C over the landmasses.
    Returns the order per biome type: biome index -> sub-type index per landmass.
    """
    orders = {}
    for t in range(n_types):
        order = [int(v) for v in rng.permutation(N_SUBTYPES)]
        while len(order) < n_landmasses:
            order += order[:n_landmasses - len(order)]
        orders[t] = order
    for r in regions:
        r.subtype_index = orders[r.biome_index][r.landmass_id - 1]
    return orders


def _attempt(land, coast, cfg, rng, recorder, attempt):
    size = land.land_mask.shape[0]
    tag = "" if attempt == 0 else f"-try{attempt + 1}"
    n_types = len(cfg.types)

    regions = _place_region_seeds(land, coast, cfg, rng)
    recorder.step(
        f"03b{tag}", "Region seeds",
        draw_dots(land.land_mask.shape, [r.seed_xy for r in regions], 4.0,
                  [(r.biome_index + 1) / n_types for r in regions]),
        "The generator scatters region seeds on the mainland of each landmass, not on the spit. The "
        "first seeds on each landmass get one biome type each, so every landmass has every biome type. "
        "Extra seeds get a random biome type. Each seed obeys the placement rule of its biome type: "
        "low, inland, or any. Spit types get no seeds: they cover the spits. "
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

    region_ids, scale = _balance_regions(land, regions, dx, dy, cfg)
    regions = _drop_empty_regions(regions, region_ids)
    n_seeded = len(regions)
    _spit_regions(land, regions, region_ids, cfg)
    recorder.step(
        f"03d{tag}", "Region IDs", region_ids,
        "Each mainland pixel goes to the nearest seed on the same landmass. The generator measures the "
        "distance from the warped pixel position, pixel + offset, to the seed, times a scale per biome "
        "type. The generator tunes the scales in a few rounds, so the seeded biome types share each "
        "landmass about equally and no biome dominates. Each spit is one region.",
        {"regions": len(regions), "seeded_regions": n_seeded, "spit_regions": len(regions) - n_seeded,
         "balance_iterations": cfg.balance_iterations, "balance_tolerance": cfg.balance_tolerance,
         "scale": {r.id: round(scale[rid], 2) for rid, r in zip(sorted(scale), regions) if rid in scale and r.id}},
    )

    problem = _validate(regions, region_ids, coast, cfg)
    if problem is not None:
        return None, problem

    orders = _assign_subtypes(regions, n_types, int(land.landmass_ids.max()), rng)
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
        "Each landmass gets one sub-type of each biome type, and no two landmasses share it. For each "
        "biome type the generator draws a random order of A, B, C over the landmasses 1, 2, 3. Every "
        "region of that biome on a landmass gets the sub-type of that landmass. The image has 16 gray "
        "levels: sea plus 15 sub-types.",
        {"sub_type_per_landmass": {cfg.types[t].name: [SUBTYPE_LETTERS[i] for i in order]
                                   for t, order in orders.items()}},
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
