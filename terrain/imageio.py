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
