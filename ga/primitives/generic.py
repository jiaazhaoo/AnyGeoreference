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


def control_point_fit(state, model: str = "affine", crs: str = "EPSG:4326", min_points: int = 3, max_rms: float | None = None,
                      fallback: str | None = None, fallback_min: int = 4):
    """Fit pixel -> map coordinates at the grid cues. The cues carry the record's coordinates, so the placement is in
    the record's datum when the record states one; `crs` is the kind's default for records that do not. With too few
    cues for `model`, `fallback` (a simpler model) is fitted when there are at least `fallback_min` cues (a frame read
    by its four corners alone: affine, two degrees of freedom left for the residual)."""
    crs = (state.sheet.record or {}).get("datum") or crs
    src, dst = _grid_cue_pairs(state)
    need = {"similarity": 2, "affine": 3, "poly2": 6}
    if len(src) < max(min_points, need[model]):
        if not fallback or len(src) < max(fallback_min, need[fallback] + 1):
            return []
        model = fallback
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


def residual_check(state, bound: float = 15.0, unit: str = "crs", geographic: bool = False):
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
    d = pred - dst
    if geographic:                                              # lon/lat degrees -> metres at the sheet's latitude
        lat0 = float(np.mean(dst[:, 1]))
        d = d * np.array([111320.0 * math.cos(math.radians(lat0)), 110574.0])
        unit = "m"
    res = np.linalg.norm(d, axis=1)
    rms = float(np.sqrt(np.mean(res ** 2)))
    return [Evidence("residual_rms", rms, "deterministic", "geometry", note=unit),
            Evidence("residual_within_bound", bool(rms <= bound), "deterministic", "geometry", note=f"bound {bound} {unit}")]


def hypothesis_agreement(state, tol_m: float = 200.0):
    """Do the two best hypotheses from *different* matchers put the sheet in the same place? Measured as the
    distance between their footprint centres in metres (geographic CRS handled). Agreement between independent
    matchers is corroboration; agreement within one matcher is not."""
    import shapely.wkt
    hs = state.hypotheses
    others = [h for h in hs[1:] if h.matcher != hs[0].matcher] if hs else []
    if not hs or not others:
        return [Evidence("matchers_agree", None, "deterministic", "geometry", note="fewer than two matchers")]
    a, b = hs[0], others[0]
    pa, pb = shapely.wkt.loads(a.site_wkt), shapely.wkt.loads(b.site_wkt)
    if pa.is_empty or pb.is_empty:
        return [Evidence("matchers_agree", None, "deterministic", "geometry", note="a footprint is empty")]
    ca, cb = pa.centroid, pb.centroid
    if a.crs.upper() in ("EPSG:4326", "WGS84"):
        lat0 = (ca.y + cb.y) / 2
        d = math.hypot((ca.x - cb.x) * 111320 * math.cos(math.radians(lat0)), (ca.y - cb.y) * 110574)
    else:
        d = float(ca.distance(cb))
    return [Evidence("matchers_agree", bool(d <= tol_m), "deterministic", "geometry", note=f"{a.matcher} vs {b.matcher}; centres {d:.1f} m apart; tol {tol_m} m"),
            Evidence("matchers_distance_m", round(d, 1), "deterministic", "geometry")]


register(Primitive("control_point_fit", "geometry", True, ("cue",), "hypothesis",
                   "least-squares fit of grid cues (printed coordinates at sheet pixels) -> transform; similarity / affine / poly2",
                   control_point_fit))
register(Primitive("residual_check", "geometry", True, ("hypothesis", "cue"), "evidence",
                   "RMS residual of the best hypothesis at the grid cues, against the kind's bound", residual_check))
register(Primitive("hypothesis_agreement", "geometry", True, ("hypothesis",), "evidence",
                   "whether the best hypotheses of two different matchers put the sheet in the same place (centres within tol_m)", hypothesis_agreement))


class SmoothWarp:
    """src -> dst as poly2 plus a smoothed thin-plate spline on its residuals: follows warps that poly2 cannot (archives
    often rectify with thin-plate splines). `scale` turns dst units into metres so `smoothing` is in metres. The
    inverse is solved by Newton's method on the forward warp, so both directions agree."""

    def __init__(self, src, dst, smoothing: float = 100.0, scale=(1.0, 1.0)):
        from scipy.interpolate import RBFInterpolator
        src, dst = np.asarray(src, float), np.asarray(dst, float)
        self.c, _ = fit_transform(src, dst, "poly2")
        self.ci, _ = fit_transform(dst, src, "poly2")
        self.k = np.asarray(scale, float)
        self.mu = src.mean(0)                                   # centred, in its own units: smoothing is scale-dependent
        r = (dst - apply_transform(self.c, src, "poly2")) * self.k
        self.rbf = RBFInterpolator(src - self.mu, r, kernel="thin_plate_spline", smoothing=smoothing)

    def __call__(self, p) -> np.ndarray:
        p = np.atleast_2d(np.asarray(p, float))
        return apply_transform(self.c, p, "poly2") + self.rbf(p - self.mu) / self.k

    def inverse(self, q, iters: int = 6) -> np.ndarray:
        q = np.atleast_2d(np.asarray(q, float))
        p = apply_transform(self.ci, q, "poly2")
        for _ in range(iters):                                  # the inverse poly2 maps dst errors back to src steps
            d = q - self(p)
            p = p + apply_transform(self.ci, q, "poly2") - apply_transform(self.ci, q - d, "poly2")
        return p


def cross_validated_error(src, dst, scale, folds: int = 4, smoothing: float = 100.0, seed: int = 0) -> np.ndarray:
    """Each pair's error (metres) when predicted by a SmoothWarp fitted without it (k-fold)."""
    src, dst = np.asarray(src, float), np.asarray(dst, float)
    idx = np.random.default_rng(seed).permutation(len(src)); e = np.zeros(len(src))
    for f in range(folds):
        te = idx[f::folds]; tr = np.setdiff1d(idx, te)
        w = SmoothWarp(src[tr], dst[tr], smoothing, scale)
        e[te] = np.linalg.norm((w(src[te]) - dst[te]) * np.asarray(scale, float), axis=1)
    return e
