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


def make_heightmap(circle: CircleResult, land: LandResult, biomes: BiomeResult,
                   cfg: HeightmapConfig, seed: int, recorder: StepRecorder) -> HeightResult:
    size = land.land_mask.shape[0]
    land_mask = land.land_mask
    profile = cfg.profile

    sea_distance = ndimage.distance_transform_edt(~land_mask).astype(np.float32)
    signed = np.where(land_mask, biomes.coast_distance, -sea_distance).astype(np.float32)
    recorder.step(
        "04a", "Signed coast distance", signed,
        "The distance to the coast. Land is positive. Sea is negative. The coast is 0.",
        {"max_land_px": round(float(signed.max()), 1), "max_sea_px": round(float(-signed.min()), 1)},
    )

    smooth_signed = ndimage.gaussian_filter(signed, sigma=cfg.coast_blur_px)
    curve = smoothstep(np.clip(smooth_signed / cfg.coast_distance_px, 0.0, 1.0)).astype(np.float32)
    curve[~land_mask] = 0.0
    recorder.step(
        "04b", "Coast curve", curve,
        "A smooth curve from 0 at the coast to 1 at coast_distance_px inland. The generator blurs "
        "the coast distance first, so the curve has no creases. The curve keeps the coast at sea level.",
        {"coast_distance_px": cfg.coast_distance_px, "coast_blur_px": cfg.coast_blur_px},
    )

    rng = np.random.default_rng([seed, STAGE, 0])
    gen = ridged_noise if profile.ridged else fractal_noise
    noise = gen((size, size), profile.octaves, profile.frequency, 2.0, 0.5, rng)
    recorder.step(
        "04c", "Height noise", noise,
        "One noise field for all biomes. Ridged noise gives sharp crests. Fractal noise gives "
        "rolling hills. All biomes share the same height profile.",
        {"frequency": profile.frequency, "octaves": profile.octaves, "ridged": profile.ridged},
    )

    land_height = np.clip(curve * (profile.base + profile.amplitude * (2.0 * noise - 1.0)), 0.0, 1.0)
    land_height = land_height.astype(np.float32)
    recorder.step(
        "04d", "Land height", land_height,
        "land = clamp(curve * (base + amplitude * (2 * noise - 1)), 0, 1). "
        "The curve multiplies the whole sum, so the coast stays at 0.",
        {"base": profile.base, "amplitude": profile.amplitude},
    )

    depth = cfg.seabed_depth
    seabed = -depth * smoothstep(np.clip(-signed / cfg.seabed_distance_px, 0.0, 1.0))
    seabed = seabed * circle.edge_band + (-depth) * (1.0 - circle.edge_band)
    seabed = ndimage.gaussian_filter(seabed.astype(np.float32), sigma=cfg.seabed_blur_px)
    seabed = seabed * circle.edge_band + (-depth) * (1.0 - circle.edge_band)
    seabed = np.minimum(seabed, 0.0).astype(np.float32)
    recorder.step(
        "04e", "Seabed", seabed,
        "The seabed goes down from 0 at the coast to the floor at seabed_distance_px. "
        "The edge band blends the seabed to the floor at the circle edge and outside the circle. "
        "A blur removes the creases between the landmasses.",
        {"seabed_depth": depth, "seabed_distance_px": cfg.seabed_distance_px,
         "seabed_blur_px": cfg.seabed_blur_px},
    )

    height = np.where(land_mask, land_height, seabed).astype(np.float32)
    recorder.step(
        "04f", "Height", height,
        "The land height and the seabed together. The image maps the floor to black and the highest "
        "point to white. Sea level is a mid gray.",
        {"min": round(float(height.min()), 3), "max": round(float(height.max()), 3)},
    )
    return HeightResult(height=height)
