"""The truth warp: poly2 plus a smoothed thin-plate spline, and its Newton inverse."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np

from ga.primitives.generic import SmoothWarp, cross_validated_error, fit_transform, apply_transform

K = (70000.0, 110574.0)


def _pairs(n=400, seed=0):
    rng = np.random.default_rng(seed)
    px = rng.uniform(0, 4500, (n, 2))
    lon = 13.5 + px[:, 0] / 4500 * 0.1667 + 2e-4 * np.sin(px[:, 1] / 700)    # a wavy warp poly2 cannot follow
    lat = 51.0 - px[:, 1] / 4500 * 0.1 + 2e-4 * np.cos(px[:, 0] / 900)
    return px, np.c_[lon, lat]


def test_spline_follows_a_warp_poly2_misses():
    px, ll = _pairs()
    c, _ = fit_transform(px, ll, "poly2")
    poly = np.linalg.norm((apply_transform(c, px, "poly2") - ll) * K, axis=1)
    e = cross_validated_error(px, ll, K)
    assert np.median(poly) > 5 and np.percentile(e, 95) < 3


def test_inverse_returns_the_pixel():
    px, ll = _pairs()
    w = SmoothWarp(px, ll, scale=K)
    q = np.array([[1000.0, 2000.0], [3500.0, 400.0], [2250.0, 2250.0]])
    assert np.abs(w.inverse(w(q)) - q).max() < 0.05
