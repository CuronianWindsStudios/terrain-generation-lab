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
