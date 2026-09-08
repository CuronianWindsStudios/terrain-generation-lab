"""Stage 2: three landmasses inside the circle."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage

from terrain.circle import CircleResult
from terrain.config import GenerationError, LandmassConfig, SpitConfig
from terrain.debug import StepRecorder, draw_dots
from terrain.noise import fractal_noise, smoothstep
from terrain.spit import make_spits

STAGE = 2


@dataclass
class LandResult:
    land_mask: np.ndarray
    landmass_ids: np.ndarray
    seeds: list[tuple[float, float]]
    seed_used: int
    spit_mask: np.ndarray = None
    spit_owner: np.ndarray = None
    spit_lengths_px: list[float] = field(default_factory=list)

    def __post_init__(self):
        shape = self.land_mask.shape
        if self.spit_mask is None:
            self.spit_mask = np.zeros(shape, dtype=bool)
        if self.spit_owner is None:
            self.spit_owner = np.zeros(shape, dtype=np.int32)


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
        "The generator places 3 seed points inside the circle. Each seed point is the center of one "
        "landmass. Rejection sampling keeps a minimum distance between the points.",
        {"seed_area_pct": cfg.seed_area_pct, "min_separation_pct": cfg.min_separation_pct,
         "seeds": [(round(x), round(y)) for x, y in seeds]},
    )

    warp_px = radius * cfg.warp_pct / 100.0
    dx = warp_px * (fractal_noise((size, size), 4, 3.0, 2.0, 0.5, rng) - 0.5) * 2.0
    dy = warp_px * (fractal_noise((size, size), 4, 3.0, 2.0, 0.5, rng) - 0.5) * 2.0
    recorder.step(
        f"02b{tag}", "Warp noise", dx,
        "Two noise fields give each pixel an offset (dx, dy). The generator measures all distances "
        "from the warped pixel position. This bends the landmass shapes and the channel between them. "
        "The image shows dx.",
        {"warp_pct": cfg.warp_pct, "warp_px": round(warp_px, 1)},
    )

    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    px = xx + dx
    py = yy + dy
    falloff = np.zeros((size, size), dtype=np.float32)
    radii = []
    distances = []
    for sx, sy in seeds:
        r = rng.uniform(cfg.radius_pct[0], cfg.radius_pct[1]) / 100.0 * radius
        radii.append(round(r, 1))
        d = np.hypot(px - sx, py - sy)
        distances.append(d)
        falloff = np.maximum(falloff, np.clip(1.0 - d / r, 0.0, 1.0))
    recorder.step(
        f"02c{tag}", "Radial falloff", falloff,
        "Each seed point gets a radial falloff: 1 at the seed point, 0 at the landmass radius. "
        "The image shows the maximum of the 3 fields.",
        {"radius_pct": list(cfg.radius_pct), "radii_px": radii},
    )

    channel_px = radius * cfg.channel_pct / 100.0
    sorted_d = np.sort(np.stack(distances), axis=0)
    channel = smoothstep(np.clip((sorted_d[1] - sorted_d[0]) / max(channel_px, 1e-6), 0.0, 1.0))
    shape_mask = (falloff * channel * circle.edge_band).astype(np.float32)
    recorder.step(
        f"02d{tag}", "Shape mask", shape_mask,
        "Each pixel belongs to its nearest seed point. Near the border between two seed points, the "
        "mask fades to 0. This makes a channel of sea between the landmasses, so they do not merge. "
        "The edge band also fades the mask to 0 at the circle edge.",
        {"channel_pct": cfg.channel_pct, "channel_px": round(channel_px, 1)},
    )

    noise = fractal_noise(
        (size, size), cfg.noise.octaves, cfg.noise.frequency,
        cfg.noise.lacunarity, cfg.noise.persistence, rng,
    )
    recorder.step(
        f"02e{tag}", "Noise", noise,
        "Fractal noise with several octaves. The noise makes the coast irregular.",
        {"octaves": cfg.noise.octaves, "frequency": cfg.noise.frequency,
         "lacunarity": cfg.noise.lacunarity, "persistence": cfg.noise.persistence},
    )

    field = noise * shape_mask
    raw_land = (field > cfg.threshold) & circle.mask
    recorder.step(
        f"02f{tag}", "Land field", field,
        "field = noise * shape_mask. Pixels with field > threshold inside the circle are land. "
        "Near a seed point the mask is 1, so most pixels are land. Near the coast the mask is small, "
        "so only high noise values are land. This makes a ragged coast.",
        {"threshold": cfg.threshold},
    )

    land = _keep_components(raw_land, cfg.count, cfg.min_lake_area_px)
    land = _fill_lakes(land, cfg.min_lake_area_px)
    recorder.step(
        f"02g{tag}", "Land mask", land,
        "The generator keeps the 3 largest connected areas. It removes islands and fills lakes "
        "smaller than min_lake_area_px.",
        {"min_lake_area_px": cfg.min_lake_area_px},
    )

    ids, count = _label_by_area(land)
    recorder.step(
        f"02h{tag}", "Landmass IDs", ids,
        "Each landmass gets an ID from 1 to 3. The largest landmass is 1. Sea is 0.",
        {"count": count, "areas_px": [int((ids == i).sum()) for i in range(1, count + 1)]},
    )
    return LandResult(land_mask=land, landmass_ids=ids, seeds=seeds, seed_used=0), count


def _add_spits(circle: CircleResult, result: LandResult, spit_cfg: SpitConfig, rng,
               recorder: StepRecorder, tag: str) -> str | None:
    """Adds one sand bar per landmass to the result. Returns a problem string when a bar does not fit."""
    spits = make_spits(circle, result, spit_cfg, rng, recorder, tag)
    if spits.problem is not None:
        return spits.problem
    result.land_mask = result.land_mask | spits.mask
    result.landmass_ids = np.where(spits.mask, spits.owner, result.landmass_ids).astype(np.int32)
    result.spit_mask = spits.mask
    result.spit_owner = spits.owner
    result.spit_lengths_px = list(spits.lengths_px)
    recorder.step(
        f"02k{tag}", "Land with sand bars", result.landmass_ids,
        "The sand bars join the land mask. Each bar pixel gets the ID of its landmass. "
        "The water behind a bar is the lagoon.",
        {"spit_px": int(spits.mask.sum())},
    )
    return None


def make_landmasses(circle: CircleResult, cfg: LandmassConfig, seed: int,
                    recorder: StepRecorder, spit_cfg: SpitConfig | None = None) -> LandResult:
    count = 0
    problem = ""
    for attempt in range(cfg.max_retries):
        rng = np.random.default_rng([seed, STAGE, attempt])
        result, count = _attempt(circle, cfg, rng, recorder, attempt)
        if count == cfg.count:
            tag = "" if attempt == 0 else f"-try{attempt + 1}"
            spit_problem = None if spit_cfg is None else _add_spits(circle, result, spit_cfg, rng, recorder, tag)
            if spit_problem is None:
                result.seed_used = seed + attempt
                return result
            problem = f"Try {attempt + 1} could not fit a sand bar: {spit_problem}."
        else:
            problem = f"Try {attempt + 1} gave {count} landmasses, not {cfg.count}."
        recorder.note(
            f"02-retry-{attempt}", "Retry",
            f"{problem} The stage tries again with the next seed.",
            {"seed": seed + attempt, "count": count},
        )
    raise GenerationError(
        f"Seed {seed} failed after {cfg.max_retries} tries. {problem} "
        "Decrease landmass.threshold, increase landmass.channel_pct, or decrease spit.min_lagoon_pct."
    )
