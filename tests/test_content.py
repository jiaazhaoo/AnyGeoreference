"""Content matching: a window found at its known offset, and the robust similarity through measurements with outliers."""
import math

import numpy as np

from ga.primitives import content as ct


def _lines(shape, n=60, seed=0):
    import cv2
    rng = np.random.default_rng(seed)
    img = np.zeros(shape, np.uint8)
    for _ in range(n):
        p = rng.integers(0, [shape[1], shape[0]], size=(2, 2))
        cv2.line(img, tuple(int(v) for v in p[0]), tuple(int(v) for v in p[1]), 255, 2)
    return img.astype(np.float32)


def test_match_finds_a_known_offset():
    ref = _lines((600, 600))
    sheet = np.zeros_like(ref)
    sheet[100:500, 100:500] = ref[100 - 7:500 - 7, 100 + 12:500 + 12]     # the sheet window sits 12 right, 7 up of ref
    dx, dy, score, distinct = ct.match(sheet, ref, (slice(150, 450), slice(150, 450)), search_px=30)
    assert abs(dx - 12) < 0.3 and abs(dy + 7) < 0.3
    assert score > 0.9 and distinct > 0.1


def test_match_refuses_an_empty_window():
    ref = _lines((300, 300))
    assert ct.match(np.zeros_like(ref), ref, (slice(50, 250), slice(50, 250)), search_px=20) is None


def test_robust_similarity_ignores_outliers():
    rng = np.random.default_rng(3)
    src = rng.uniform(0, 10000, 12) + 1j * rng.uniform(0, 10000, 12)
    m, t = 1.01 * np.exp(1j * math.radians(1.5)), 250 - 180j
    dst = m * src + t + (rng.normal(0, 5, 12) + 1j * rng.normal(0, 5, 12))
    dst[[2, 7]] += 900                                                   # two windows on the wrong river
    mf, tf, mask = ct._robust(src, dst, 40.0)
    assert not mask[2] and not mask[7] and mask.sum() == 10
    assert abs(mf - m) < 0.002 and abs(tf - t) < 30


def test_loo_prefers_affine_for_a_sheared_sheet():
    rng = np.random.default_rng(5)
    src = rng.uniform(0, 10000, 9) + 1j * rng.uniform(0, 10000, 9)
    dst = (src.real * 1.004 + src.imag * 0.006 + 30) + 1j * (src.real * -0.001 + src.imag * 0.995 - 40)
    idx = list(range(9))
    assert max(ct._loo(src, dst, idx, "affine")) < 1.0 < max(ct._loo(src, dst, idx, "similarity"))
