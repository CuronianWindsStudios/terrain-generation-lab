"""Stage 4: the heightmap."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from terrain.biomes import BiomeResult
from terrain.circle import CircleResult
from terrain.config import HeightmapConfig, Profile
from terrain.debug import StepRecorder
from terrain.landmass import LandResult
from terrain.noise import NOISE_GENERATORS, smoothstep

STAGE = 4


@dataclass
class HeightResult:
    height: np.ndarray


def biome_noise(profile: Profile, size: int, seed: int, biome_index: int) -> np.ndarray:
    """The noise field of one biome type at the map size. Each biome has its own random stream."""
    rng = np.random.default_rng([seed, STAGE, biome_index])
    gen = NOISE_GENERATORS[profile.noise]
    return gen((size, size), profile.octaves, profile.frequency, profile.lacunarity, profile.persistence, rng)


def biome_weights(biome_ids: np.ndarray, blend_px: list[float]) -> np.ndarray:
    """One blurred mask per biome type, each with its own blur. Normalized to sum 1 where the sum is positive."""
    masks = [
        ndimage.gaussian_filter((biome_ids == i + 1).astype(np.float32), sigma=blur)
        for i, blur in enumerate(blend_px)
    ]
    blurred = np.stack(masks)
    total = blurred.sum(axis=0, keepdims=True)
    return (blurred / np.maximum(total, 1e-6)).astype(np.float32)


def make_heightmap(circle: CircleResult, land: LandResult, biomes: BiomeResult,
                   cfg: HeightmapConfig, seed: int, recorder: StepRecorder,
                   spit_rise_px: float = 6.0) -> HeightResult:
    size = land.land_mask.shape[0]
    land_mask = land.land_mask
    names = biomes.type_names
    profiles = [cfg.profiles[n] for n in names]

    sea_distance = ndimage.distance_transform_edt(~land_mask).astype(np.float32)
    signed = np.where(land_mask, biomes.coast_distance, -sea_distance).astype(np.float32)
    recorder.step(
        "04a", "Signed coast distance", signed,
        "The distance to the coast. Land is positive. Sea is negative. The coast is 0.",
        {"max_land_px": round(float(signed.max()), 1), "max_sea_px": round(float(-signed.min()), 1)},
    )

    smooth_signed = ndimage.gaussian_filter(signed, sigma=cfg.coast_blur_px)
    curve = smoothstep(np.clip(smooth_signed / cfg.coast_distance_px, 0.0, 1.0)).astype(np.float32)
    spit_curve = smoothstep(np.clip(biomes.coast_distance / spit_rise_px, 0.0, 1.0)).astype(np.float32)
    curve = np.where(land.spit_mask, spit_curve, curve)
    curve[~land_mask] = 0.0
    recorder.step(
        "04b", "Coast curve", curve,
        "A smooth curve from 0 at the coast to 1 at coast_distance_px inland. The generator blurs "
        "the coast distance first, so the curve has no creases. The curve keeps the coast at sea level. "
        "A spit is narrow, so on the spit the curve reaches 1 at the short spit rise distance instead.",
        {"coast_distance_px": cfg.coast_distance_px, "coast_blur_px": cfg.coast_blur_px,
         "spit_rise_px": spit_rise_px},
    )

    weights = biome_weights(biomes.biome_ids, [p.blend_px for p in profiles])
    spit = land.spit_mask
    if spit.any():
        # a spit is narrow, so it keeps its own profile: the mainland profiles do not blend into it
        weights[:, spit] = 0.0
        weights[biomes.biome_ids[spit] - 1, np.nonzero(spit)[0], np.nonzero(spit)[1]] = 1.0
    base_map = np.zeros((size, size), dtype=np.float32)
    amp_map = np.zeros((size, size), dtype=np.float32)
    noise_map = np.zeros((size, size), dtype=np.float32)
    for i, p in enumerate(profiles):
        base_map += weights[i] * p.base
        amp_map += weights[i] * p.amplitude
        noise_map += weights[i] * biome_noise(p, size, seed, i)
    recorder.step(
        "04c", "Profile base", base_map,
        "Each biome type has its own height profile. The base is the lowest height of the biome. "
        "A base below 0 makes pools below the sea level. The generator blurs each biome mask with "
        "the blend_px of that biome and mixes the profiles, so the height changes smoothly at "
        "biome borders. Spit pixels keep the spit profile only. This image is the mixed base height.",
        {"base": {n: p.base for n, p in zip(names, profiles)},
         "blend_px": {n: p.blend_px for n, p in zip(names, profiles)}},
    )
    recorder.step(
        "04c-2", "Profile amplitude", amp_map,
        "The mixed noise amplitude of the biome profiles. The amplitude is the height of the "
        "hills above the base.",
        {"amplitude": {n: p.amplitude for n, p in zip(names, profiles)}},
    )
    recorder.step(
        "04d", "Biome noise", noise_map,
        "One noise field per biome type, mixed with the same weights. Ridged noise gives sharp "
        "crests. Billow noise gives round bulges. Fractal noise gives rolling hills.",
        {n: f"{p.noise}, frequency {p.frequency}, octaves {p.octaves}, "
            f"lacunarity {p.lacunarity}, persistence {p.persistence}" for n, p in zip(names, profiles)},
    )

    land_height = np.clip(curve * (base_map + amp_map * noise_map), -1.0, 1.0).astype(np.float32)
    recorder.step(
        "04e", "Land height", land_height,
        "land = clamp(curve * (base + amplitude * noise), -1, 1). The noise is in [0, 1], so the "
        "hills go up from the base. The curve multiplies the whole sum, so the coast stays at 0.",
    )

    depth = cfg.seabed_depth
    seabed = -depth * smoothstep(np.clip(-signed / cfg.seabed_distance_px, 0.0, 1.0))
    seabed = seabed * circle.edge_band + (-depth) * (1.0 - circle.edge_band)
    seabed = ndimage.gaussian_filter(seabed.astype(np.float32), sigma=cfg.seabed_blur_px)
    seabed = seabed * circle.edge_band + (-depth) * (1.0 - circle.edge_band)
    seabed = np.minimum(seabed, 0.0).astype(np.float32)
    recorder.step(
        "04f", "Seabed", seabed,
        "The seabed goes down from 0 at the coast to the floor at seabed_distance_px. "
        "The edge band blends the seabed to the floor at the circle edge and outside the circle. "
        "A blur removes the creases between the landmasses.",
        {"seabed_depth": depth, "seabed_distance_px": cfg.seabed_distance_px,
         "seabed_blur_px": cfg.seabed_blur_px},
    )

    height = np.where(land_mask, land_height, seabed).astype(np.float32)
    recorder.step(
        "04g", "Height", height,
        "The land height and the seabed together. The image maps the floor to black and the highest "
        "point to white. Sea level is a mid gray.",
        {"min": round(float(height.min()), 3), "max": round(float(height.max()), 3)},
    )
    return HeightResult(height=height)
