"""Stage 2, second part: one sand bar per landmass.

The bar is a strip of land that runs along the coast at the lagoon distance and joins the coast at
both ends, like the Curonian Spit. Across a bay it runs over the bay mouth, so the bay becomes the
lagoon. Along an open coast it runs parallel to the coast, so a narrow lagoon lies behind it, like
a barrier island. A strait at one end keeps the lagoon open to the sea, and the bar tapers to a
point there.

The path follows a level line of the distance field of the closed land shape. The closing fills
the bays, so the level line crosses the bay mouths. The level ramps up from 0 at the start and
back down to 0 at the end, so the bar leaves and rejoins the coast at a tangent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from terrain.circle import CircleResult
from terrain.config import SpitConfig
from terrain.debug import StepRecorder, draw_dots
from terrain.noise import fractal_noise, smoothstep

if TYPE_CHECKING:
    from terrain.landmass import LandResult

EIGHT = np.ones((3, 3), dtype=bool)
STEP_PX = 2.0
STARTS = 8
TAPER = 5.0          # taper length at the strait tip, in bar widths


@dataclass
class SpitResult:
    mask: np.ndarray
    owner: np.ndarray
    lengths_px: list[float] = field(default_factory=list)
    anchors: list[tuple[tuple[float, float], tuple[float, float]]] = field(default_factory=list)
    paths: list[np.ndarray] = field(default_factory=list)
    problem: str | None = None


@dataclass
class _Sizes:
    """The bar sizes in pixels at this circle radius."""
    bay: float
    lagoon: float
    length: tuple[float, float]
    width: float
    strait: float
    edge_noise: float
    gap: float


def _sizes(cfg: SpitConfig, radius: float) -> _Sizes:
    r = radius / 100.0
    return _Sizes(cfg.bay_pct * r, cfg.lagoon_pct * r, (cfg.length_pct[0] * r, cfg.length_pct[1] * r),
                  cfg.width_pct * r, cfg.strait_pct * r, cfg.edge_noise_pct * r, cfg.gap_pct * r)


def closing(mask: np.ndarray, radius: float) -> np.ndarray:
    """Morphological closing with a disk: a dilation, then an erosion, both by the radius. Fills bays."""
    if radius <= 0:
        return mask.copy()
    dilated = ndimage.distance_transform_edt(~mask) <= radius
    return ndimage.distance_transform_edt(dilated) > radius - 0.5


def _at(fieldmap: np.ndarray, p: np.ndarray) -> float:
    return float(ndimage.map_coordinates(fieldmap, [[p[1]], [p[0]]], order=1, mode="nearest")[0])


def _march(start: np.ndarray, sign: float, dist: np.ndarray, gy: np.ndarray, gx: np.ndarray,
           d_main: np.ndarray, room: np.ndarray, inside: np.ndarray, lagoon: float, length: float,
           min_room: float) -> np.ndarray:
    """Follows the level line of dist at the lagoon level from start, for the given length.

    The level ramps up from the coast over the first ramp and back down over the last ramp. After
    the ramp down, the march goes on at level 0 until the point touches the mainland again, so the
    bar rejoins the coast. Returns the points, start included.
    """
    size = dist.shape[0]
    ramp = min(3.0 * lagoon, length / 4.0)
    points = [start.copy()]
    p = start.copy()
    travelled = 0.0
    while travelled < length + 3.0 * ramp:
        g = np.array([_at(gx, p), _at(gy, p)])
        norm = float(np.hypot(g[0], g[1]))
        if norm < 1e-6:
            break
        g /= norm
        tangent = np.array([-g[1], g[0]]) * sign
        s = travelled + STEP_PX
        up = smoothstep(min(s / ramp, 1.0))
        down = smoothstep(float(np.clip((length - s) / ramp, 0.0, 1.0)))
        level = lagoon * up * down
        q = p + STEP_PX * tangent
        q = q + (level - _at(dist, q)) * g
        jump = float(np.hypot(*(q - p)))
        if jump > 1.5 * STEP_PX:
            q = p + (q - p) * (1.5 * STEP_PX / jump)
        if not (1 <= q[0] < size - 2 and 1 <= q[1] < size - 2):
            break
        if _at(room, q) < min_room or _at(inside, q) < 0.5:
            break
        travelled += float(np.hypot(*(q - p)))
        p = q
        points.append(p.copy())
        if s > length and _at(d_main, q) <= 1.5:
            break
    return np.array(points)


def _path_length(path: np.ndarray) -> float:
    return float(np.hypot(*np.diff(path, axis=0).T).sum()) if len(path) > 1 else 0.0


def _rasterize(path: np.ndarray, width: np.ndarray, edge_noise: np.ndarray, size: int,
               factor: np.ndarray | None = None) -> np.ndarray:
    """The strip around the path. The width map gives the full width at each pixel, and the
    factor scales it per path point, for the taper at the tip."""
    pad = int(np.ceil(float(width.max()) + float(np.abs(edge_noise).max()) + 2))
    x0 = max(int(path[:, 0].min()) - pad, 0)
    x1 = min(int(path[:, 0].max()) + pad + 1, size)
    y0 = max(int(path[:, 1].min()) - pad, 0)
    y1 = min(int(path[:, 1].max()) + pad + 1, size)
    yy, xx = np.mgrid[y0:y1, x0:x1]
    ys, xs = yy.ravel(), xx.ravel()
    d, idx = cKDTree(path).query(np.column_stack([xs, ys]).astype(np.float32))
    half = width[ys, xs] / 2.0
    if factor is not None:
        half = half * factor[idx]
    limit = np.maximum(half + edge_noise[ys, xs], 0.5 * half)
    hit = d <= limit
    mask = np.zeros((size, size), dtype=bool)
    mask[ys[hit], xs[hit]] = True
    return mask


def _lagoon_area(bar: np.ndarray, land: np.ndarray) -> int:
    """The sea area the bar encloses: sea pieces beside the bar that do not reach the image corner."""
    sea = ~(land | bar)
    labels, _ = ndimage.label(sea)
    open_sea = labels[0, 0]
    beside = ndimage.binary_dilation(bar, structure=EIGHT, iterations=2) & sea
    enclosed = [int(v) for v in np.unique(labels[beside]) if v not in (0, open_sea)]
    return int(np.isin(labels, enclosed).sum()) if enclosed else 0


def _strait(path: np.ndarray, end: int, px: _Sizes) -> tuple[np.ndarray, np.ndarray]:
    """Cuts the path short of the coast at the given end and tapers the width to a point there.
    Returns the shortened path and the width factor per point."""
    if end == 0:
        path = path[::-1]
    seg = np.hypot(*np.diff(path, axis=0).T)
    from_tip = np.concatenate([[0.0], np.cumsum(seg)])[::-1]   # path distance to the cut end
    keep = from_tip > px.strait + px.width / 2.0
    path = path[keep]
    from_tip = from_tip[keep] - (px.strait + px.width / 2.0)
    factor = 0.15 + 0.85 * smoothstep(np.clip(from_tip / (TAPER * px.width), 0.0, 1.0))
    return path, factor.astype(np.float32)


def _join_ends(path: np.ndarray, mainland: np.ndarray) -> np.ndarray:
    """Extends both ends of the path onto the nearest mainland pixel, so the bar touches the coast."""
    _, idx = ndimage.distance_transform_edt(~mainland, return_indices=True)
    out = [path]
    for end in (0, -1):
        p = path[end]
        y, x = int(round(p[1])), int(round(p[0]))
        y = min(max(y, 0), mainland.shape[0] - 1)
        x = min(max(x, 0), mainland.shape[1] - 1)
        target = np.array([float(idx[1][y, x]), float(idx[0][y, x])])
        n = max(int(np.ceil(np.hypot(*(target - p)) / STEP_PX)), 1)
        seg = p[None, :] + (target - p)[None, :] * (np.arange(1, n + 1) / n)[:, None]
        out = [seg[::-1]] + out if end == 0 else out + [seg]
    return np.vstack(out)


def _one_bar(lm: int, land: LandResult, circle: CircleResult, taken: np.ndarray, px: _Sizes,
             cfg: SpitConfig, rng, edge_noise: np.ndarray, width: np.ndarray):
    """Returns (mask, anchors, path, length) or a problem string."""
    size = land.land_mask.shape[0]
    mainland = land.landmass_ids == lm
    d_main = ndimage.distance_transform_edt(~mainland).astype(np.float32)
    closed = closing(mainland, px.bay)
    dist = ndimage.gaussian_filter(ndimage.distance_transform_edt(~closed).astype(np.float32), sigma=2.0)
    gy, gx = np.gradient(dist)
    other = ((land.landmass_ids > 0) & ~mainland) | taken
    room = ndimage.distance_transform_edt(~other).astype(np.float32)
    inside = (circle.edge_band > 0.5).astype(np.float32)
    min_room = px.gap + px.width
    all_land = (land.landmass_ids > 0) | taken
    min_lagoon = cfg.min_lagoon_pct / 100.0 * float(mainland.sum())

    # start points: outer coast pixels, on the boundary of the closed shape, with room around them
    outer = mainland & (ndimage.distance_transform_edt(closed) <= 2.5)
    coast = outer & (room >= min_room) & (inside > 0.5)
    ys, xs = np.nonzero(coast)
    if len(ys) == 0:
        return f"landmass {lm} has no coast with room for a sand bar"

    best = None
    short = 0
    small = 0
    for _ in range(STARTS):
        k = int(rng.integers(0, len(ys)))
        start = np.array([float(xs[k]), float(ys[k])])
        length = float(rng.uniform(px.length[0], px.length[1]))
        for sign in (1.0, -1.0):
            path = _march(start, sign, dist, gy, gx, d_main, room, inside, px.lagoon, length, min_room)
            got = _path_length(path)
            if got < 0.6 * length or _at(d_main, path[-1]) > 3.0:
                short += 1
                continue
            bar = _rasterize(path, width, edge_noise, size) & circle.mask & ~all_land
            area = _lagoon_area(bar, all_land)
            if area < min_lagoon:
                small += 1
                continue
            if best is None or area > best[0]:
                best = (area, path)
    if best is None:
        return (f"landmass {lm}: no sand bar fits. {2 * STARTS} paths tried, {short} stopped early, "
                f"{small} enclosed fewer than {int(min_lagoon)} px")
    _, path = best
    path = _join_ends(path, mainland)
    anchors = (tuple(path[0]), tuple(path[-1]))
    length = _path_length(path)

    factor = None
    if px.strait > 0:
        path, factor = _strait(path, int(rng.integers(0, 2)), px)
    bar = _rasterize(path, width, edge_noise, size, factor) & circle.mask & ~all_land
    joined, _ = ndimage.label(bar | mainland)
    bar &= np.isin(joined, np.unique(joined[mainland]))
    if not bar.any():
        return f"landmass {lm}: the strait removed the whole bar"
    return bar, anchors, path, length


def make_spits(circle: CircleResult, land: LandResult, cfg: SpitConfig, rng,
               recorder: StepRecorder, tag: str = "") -> SpitResult:
    size = land.land_mask.shape[0]
    px = _sizes(cfg, circle.radius)
    edge_noise = (px.edge_noise * (fractal_noise((size, size), 3, 24.0, 2.0, 0.5, rng) - 0.5) * 2.0)
    width = px.width * (1.0 + cfg.width_variation * (fractal_noise((size, size), 2, 6.0, 2.0, 0.5, rng) - 0.5) * 2.0)
    edge_noise = edge_noise.astype(np.float32)
    width = width.astype(np.float32)
    mask = np.zeros((size, size), dtype=bool)
    owner = np.zeros((size, size), dtype=np.int32)
    result = SpitResult(mask, owner)
    n = int(land.landmass_ids.max())
    for lm in range(1, n + 1):
        got = _one_bar(lm, land, circle, mask, px, cfg, rng, edge_noise, width)
        if isinstance(got, str):
            result.problem = got
            return result
        m, anchors, path, length = got
        mask |= m
        owner[m] = lm
        result.anchors.append(anchors)
        result.paths.append(path)
        result.lengths_px.append(length)

    dots = draw_dots((size, size), [p for pair in result.anchors for p in pair], 5.0)
    for path in result.paths:
        xs = np.clip(np.round(path[:, 0]).astype(int), 0, size - 1)
        ys = np.clip(np.round(path[:, 1]).astype(int), 0, size - 1)
        dots[ys, xs] = np.maximum(dots[ys, xs], 0.6)
    recorder.step(
        f"02i{tag}", "Bar paths", dots,
        "Each landmass gets one sand bar. The bright dots are the two ends on the coast. The line is "
        "the path: it follows a level line of the distance field of the closed land shape at the "
        "lagoon distance. The closing fills the bays, so the path crosses the bay mouths. The level "
        "ramps up from 0 at the start and back down to 0 at the end, so the bar leaves and rejoins "
        "the coast at a tangent. The generator tries several start points in both directions and "
        "keeps the path that encloses the most water.",
        {"bay_pct": cfg.bay_pct, "lagoon_pct": cfg.lagoon_pct, "length_pct": list(cfg.length_pct),
         "min_lagoon_pct": cfg.min_lagoon_pct, "gap_pct": cfg.gap_pct,
         "length_px": [round(v) for v in result.lengths_px]},
    )
    recorder.step(
        f"02j{tag}", "Sand bars", mask,
        "The sand bar is a strip around the path. The width varies along the bar with low-frequency "
        "noise, and edge noise makes the coast ragged. At the strait the bar stops short of the coast "
        "and tapers to a point, so the lagoon stays open to the sea.",
        {"width_pct": cfg.width_pct, "width_px": round(px.width, 1), "width_variation": cfg.width_variation,
         "strait_pct": cfg.strait_pct, "edge_noise_pct": cfg.edge_noise_pct},
    )
    return result
