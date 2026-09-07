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
