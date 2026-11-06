"""Generic primitives: pure numpy, no data source. These are the ones every kind shares."""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from ..model import Cue, Hypothesis
from . import Primitive, register
from evalcore import Evidence


# -- transforms --------------------------------------------------------------------------------------------------
def _design(xy: np.ndarray, order: int) -> np.ndarray:
    x, y = xy[:, 0], xy[:, 1]
    cols = [np.ones_like(x), x, y]
    if order >= 2:
        cols += [x * x, x * y, y * y]
    return np.stack(cols, axis=1)


def fit_transform(src: np.ndarray, dst: np.ndarray, model: str = "affine") -> tuple[np.ndarray, np.ndarray]:
    """Least-squares src -> dst. model: 'similarity' (4 dof), 'affine' (6), 'poly2' (12). Returns (coeffs, residuals)."""
    src, dst = np.asarray(src, float), np.asarray(dst, float)
    if model == "similarity":
        # [x'] = [a -b][x] + [c]; solve for a, b, c, d
        A = np.zeros((2 * len(src), 4)); B = dst.reshape(-1)
        A[0::2, 0], A[0::2, 1], A[0::2, 2] = src[:, 0], -src[:, 1], 1
        A[1::2, 0], A[1::2, 1], A[1::2, 3] = src[:, 1], src[:, 0], 1
        a, b, c, d = np.linalg.lstsq(A, B, rcond=None)[0]
        coeffs = np.array([[a, -b, c], [b, a, d]])
        pred = (coeffs[:, :2] @ src.T).T + coeffs[:, 2]
    else:
        order = 1 if model == "affine" else 2
        D = _design(src, order)
        coeffs = np.linalg.lstsq(D, dst, rcond=None)[0]          # (k, 2)
        pred = D @ coeffs
    res = np.linalg.norm(pred - dst, axis=1)
    return coeffs, res


def apply_transform(coeffs: np.ndarray, pts: np.ndarray, model: str = "affine") -> np.ndarray:
    pts = np.asarray(pts, float)
    if model == "similarity":
        return (coeffs[:, :2] @ pts.T).T + coeffs[:, 2]
    order = 1 if model == "affine" else 2
    return _design(pts, order) @ coeffs


def affine6(coeffs: np.ndarray, model: str) -> tuple[float, ...]:
    """The 6-coefficient affine the Hypothesis carries (poly2 keeps its linear part here; full coeffs in `note`)."""
    if model == "similarity":
        a, b, c = coeffs[0]; d, e, f = coeffs[1]
        return (a, b, c, d, e, f)
    c = coeffs
    return (c[1, 0], c[2, 0], c[0, 0], c[1, 1], c[2, 1], c[0, 1])


# -- primitives ----------------------------------------------------------------------------------------------------
def _grid_cue_pairs(state) -> tuple[np.ndarray, np.ndarray]:
    """Grid cues carry their printed coordinate as text 'x,y' and their sheet pixel as the bbox centre."""
    src, dst = [], []
    for c in state.cues:
        if c.kind == "grid" and "," in c.text:
            x0, y0, x1, y1 = c.bbox
            src.append(((x0 + x1) / 2, (y0 + y1) / 2))
            dst.append(tuple(float(v) for v in c.text.split(",")[:2]))
    return np.array(src, float), np.array(dst, float)


def control_point_fit(state, model: str = "affine", crs: str = "EPSG:4326", min_points: int = 3, max_rms: float | None = None):
    src, dst = _grid_cue_pairs(state)
    need = {"similarity": 2, "affine": 3, "poly2": 6}[model]
    if len(src) < max(min_points, need):
        return []
    coeffs, res = fit_transform(src, dst, model)
    rms = float(np.sqrt(np.mean(res ** 2)))
    if max_rms is not None and rms > max_rms:
        return []
    W = state.sheet.meta.get("width", 0); H = state.sheet.meta.get("height", 0)
    corners = apply_transform(coeffs, np.array([[0, 0], [W, 0], [W, H], [0, H]], float), model) if W and H else None
    wkt = "POLYGON((" + ",".join(f"{x} {y}" for x, y in corners) + f",{corners[0][0]} {corners[0][1]}))" if corners is not None else "POLYGON EMPTY"
    score = 1.0 / (1.0 + rms)
    return [Hypothesis(state.sheet.digest, affine6(coeffs, model), wkt, crs, score, "control_point_fit", (),
                       note=f"{model}; n={len(src)}; rms={rms:.4g}; coeffs={coeffs.tolist()}")]


def residual_check(state, bound: float = 15.0, unit: str = "crs"):
    """Residual of the best hypothesis at the grid cues, as evidence. `bound` is in CRS units (or metres if the
    hypothesis note says so); the recipe sets it per kind."""
    if not state.hypotheses:
        return []
    h = state.hypotheses[0]
    src, dst = _grid_cue_pairs(state)
    if len(src) == 0:
        return []
    model = "poly2" if h.note.startswith("poly2") else "similarity" if h.note.startswith("similarity") else "affine"
    try:
        import ast
        coeffs = np.array(ast.literal_eval(h.note.split("coeffs=")[1]))
    except Exception:                                           # noqa: BLE001
        a, b, c, d, e, f = h.transform                       # x' = a x + b y + c ; y' = d x + e y + f
        coeffs = np.array([[c, f], [a, d], [b, e]])
        model = "affine"
    pred = apply_transform(coeffs, src, model)
    res = np.linalg.norm(pred - dst, axis=1)
    rms = float(np.sqrt(np.mean(res ** 2)))
    return [Evidence("residual_rms", rms, "deterministic", "geometry"),
            Evidence("residual_within_bound", bool(rms <= bound), "deterministic", "geometry", note=f"bound {bound} {unit}")]


def hypothesis_agreement(state, tol: float = 0.5):
    """Do the top two hypotheses (from different matchers) agree? Independent matchers agreeing is corroboration."""
    hs = state.hypotheses
    if len(hs) < 2:
        return [Evidence("matchers_agree", None, "deterministic", "geometry", note="fewer than two hypotheses")]
    a, b = hs[0], hs[1]
    same_matcher = a.matcher == b.matcher
    d = float(np.linalg.norm(np.array(a.transform) - np.array(b.transform)))
    return [Evidence("matchers_agree", bool(d <= tol and not same_matcher), "deterministic", "geometry",
                     note=f"{a.matcher} vs {b.matcher}; transform distance {d:.3g}")]


register(Primitive("control_point_fit", "geometry", True, ("cue",), "hypothesis",
                   "least-squares fit of grid cues (printed coordinates at sheet pixels) -> transform; similarity / affine / poly2",
                   control_point_fit))
register(Primitive("residual_check", "geometry", True, ("hypothesis", "cue"), "evidence",
                   "RMS residual of the best hypothesis at the grid cues, against the kind's bound", residual_check))
register(Primitive("hypothesis_agreement", "geometry", True, ("hypothesis",), "evidence",
                   "whether two hypotheses from different matchers agree", hypothesis_agreement))
