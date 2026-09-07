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
    names = biomes.type_names
    n_types = len(names)

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
    for i, name in enumerate(names):
        p = cfg.profiles[name]
        base_map += weights[i] * p.base
        amp_map += weights[i] * p.amplitude
        rng = np.random.default_rng([seed, STAGE, i])
        gen = ridged_noise if p.ridged else fractal_noise
        noise_map += weights[i] * gen((size, size), p.octaves, p.frequency, 2.0, 0.5, rng)
    recorder.step(
        "04c", "Profile base", base_map,
        "Each biome type has a height profile with a base height and a noise amplitude. The generator "
        "blurs the biome masks with profile_blur_px and mixes the profiles, so the height changes "
        "smoothly at biome borders. This image is the base height.",
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
        {n: f"frequency {cfg.profiles[n].frequency}, octaves {cfg.profiles[n].octaves}, "
            f"ridged {cfg.profiles[n].ridged}" for n in names},
    )

    land_height = np.clip(curve * (base_map + amp_map * (2.0 * noise_map - 1.0)), 0.0, 1.0)
    land_height = land_height.astype(np.float32)
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
