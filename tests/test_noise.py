import numpy as np

from terrain.noise import billow_noise, fractal_noise, ridged_noise, smoothstep, value_noise


def test_smoothstep_ends():
    assert smoothstep(np.float32(0.0)) == 0.0
    assert smoothstep(np.float32(1.0)) == 1.0
    assert abs(smoothstep(np.float32(0.5)) - 0.5) < 1e-6


def test_value_noise_shape_and_range():
    rng = np.random.default_rng(1)
    n = value_noise((64, 96), 3.0, rng)
    assert n.shape == (64, 96)
    assert n.dtype == np.float32
    assert n.min() >= 0.0 and n.max() <= 1.0


def test_fractal_noise_range_and_determinism():
    a = fractal_noise((64, 64), 5, 3.0, 2.0, 0.5, np.random.default_rng(3))
    b = fractal_noise((64, 64), 5, 3.0, 2.0, 0.5, np.random.default_rng(3))
    assert a.min() >= 0.0 and a.max() <= 1.0
    assert np.array_equal(a, b)
    assert a.std() > 0.01


def test_ridged_noise_range():
    n = ridged_noise((64, 64), 4, 4.0, 2.0, 0.5, np.random.default_rng(5))
    assert n.min() >= 0.0 and n.max() <= 1.0


def test_billow_noise_is_the_inverse_of_ridged():
    r = ridged_noise((64, 64), 4, 4.0, 2.0, 0.5, np.random.default_rng(5))
    b = billow_noise((64, 64), 4, 4.0, 2.0, 0.5, np.random.default_rng(5))
    assert b.min() >= 0.0 and b.max() <= 1.0
    assert np.allclose(r + b, 1.0, atol=1e-5)
