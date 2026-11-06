"""matcher-polyline-shape (verification half): once a hypothesis has been fitted, check it against a long
distinctive line on the sheet -- a coastline, a river, a railway -- independently of names and the graticule.
The sheet's land/water boundary (an ink-colour mask, a traced skeleton, or Canny edges -- whichever linework layer
is on the state) is carried through the fitted hypothesis's transform into the reference CRS and scored against a
distance transform of a modern reference shoreline/polyline layer for the candidate area (chamfer distance).
Stretches that sit far from any reference line (docks, reclaimed foreshore, a straightened river) are clipped out
as outliers rather than counted against the fit, per matcher-polyline-shape. A chamfer score alone means nothing
without its chance level, so the same points are also scored shifted by a few hundred metres and a margin is
required; a straight reference line is rejected by a curvature (sinuosity) guard, since a straight line matches
everywhere. See matcher-polyline-shape and family-nautical-charts in the knowledge base."""
from __future__ import annotations

import numpy as np

from .. import Primitive, register
from evalcore import Evidence

SHEET_LAYER_NAMES = ("water_mask", "coastline_mask", "shoreline_mask", "line_structure", "edges")
REFERENCE_LAYER_NAMES = ("reference_vectors", "reference_shoreline", "reference_polylines")


def _points_of(obj) -> np.ndarray:
    """Coordinates of a shapely-like geometry, a polyline array, or anything with .coords / .geoms."""
    if hasattr(obj, "geoms"):
        parts = [p for p in (_points_of(g) for g in obj.geoms) if len(p)]
        return np.concatenate(parts, axis=0) if parts else np.zeros((0, 2))
    if hasattr(obj, "coords"):
        return np.asarray(list(obj.coords), float)
    return np.asarray(obj, float).reshape(-1, 2)


def _sheet_points(layer, max_points: int, seed: int = 0) -> np.ndarray:
    if layer.kind == "mask":
        ys, xs = np.nonzero(np.asarray(layer.data) > 0)
        pts = np.column_stack([xs, ys]).astype(float)
    else:                                                          # "polylines" or "vectors"
        parts = [p for p in (_points_of(o) for o in layer.data) if len(p)]
        pts = np.concatenate(parts, axis=0) if parts else np.zeros((0, 2))
    if len(pts) > max_points:
        rng = np.random.default_rng(seed)
        pts = pts[rng.choice(len(pts), max_points, replace=False)]
    return pts


def _bounds(geoms) -> tuple[float, float, float, float]:
    x0 = y0 = float("inf"); x1 = y1 = float("-inf")
    for g in geoms:
        gx0, gy0, gx1, gy1 = g.bounds if hasattr(g, "bounds") else (lambda p: (p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()))(_points_of(g))
        x0, y0, x1, y1 = min(x0, gx0), min(y0, gy0), max(x1, gx1), max(y1, gy1)
    return x0, y0, x1, y1


def _rasterize(geoms, bbox, res_m: float, width_px: int = 1):
    import cv2
    x0, y0, x1, y1 = bbox
    W = max(2, min(4000, int(round((x1 - x0) / res_m))))
    H = max(2, min(4000, int(round((y1 - y0) / res_m))))
    img = np.zeros((H, W), np.uint8)
    for g in geoms:
        parts = getattr(g, "geoms", [g])
        for part in parts:
            coords = _points_of(part)
            if len(coords) < 2:
                continue
            px = (coords[:, 0] - x0) / res_m
            py = (y1 - coords[:, 1]) / res_m
            cv2.polylines(img, [np.column_stack([px, py]).round().astype(np.int32)], False, 255, width_px)
    return img, W, H


def _sinuosity(geoms) -> float:
    """Arc length / straight-line endpoint distance, the largest over the reference geometries; 1.0 is a
    straight line, higher means bends -- the curvature guard."""
    best = 1.0
    for g in geoms:
        parts = getattr(g, "geoms", [g])
        for part in parts:
            pts = _points_of(part)
            if len(pts) < 2:
                continue
            length = float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)))
            span = float(np.linalg.norm(pts[-1] - pts[0]))
            if span > 1e-6:
                best = max(best, length / span)
    return best


def _chamfer(dist_m: np.ndarray, bbox, res_m: float, pts_crs: np.ndarray, off_grid_m: float) -> np.ndarray:
    x0, y0, x1, y1 = bbox
    H, W = dist_m.shape
    gx = np.round((pts_crs[:, 0] - x0) / res_m).astype(int)
    gy = np.round((y1 - pts_crs[:, 1]) / res_m).astype(int)
    inside = (gx >= 0) & (gx < W) & (gy >= 0) & (gy < H)
    out = np.full(len(pts_crs), off_grid_m)
    out[inside] = dist_m[gy[inside], gx[inside]]
    return out


def _apply(transform, pts: np.ndarray) -> np.ndarray:
    a, b, c, d, e, f = transform
    x, y = pts[:, 0], pts[:, 1]
    return np.column_stack([a * x + b * y + c, d * x + e * y + f])


def polyline_shape_match(state, tol_m: float = 25.0, outlier_tol_m: float = 150.0, res_m: float = 5.0,
                         shift_m: float = 300.0, margin_m: float = 10.0, pad_m: float = 500.0,
                         min_sinuosity: float = 1.05, max_points: int = 4000, min_points: int = 15):
    """Chamfer-match the sheet's land/water boundary (or any traced linework) against a reference polyline layer
    under the best hypothesis's transform; report the matched fraction after clipping outliers (reclaimed
    stretches), the chance-level margin, and whether the reference line has curvature at all."""
    if not state.hypotheses:
        return []
    h = state.hypotheses[0]
    sheet_layer = next((state.layer(n) for n in SHEET_LAYER_NAMES if state.layer(n) is not None), None)
    ref_layer = next((state.layer(n) for n in REFERENCE_LAYER_NAMES if state.layer(n) is not None), None)
    if sheet_layer is None or ref_layer is None or not ref_layer.data:
        return []

    sheet_pts = _sheet_points(sheet_layer, max_points)
    if len(sheet_pts) < min_points:
        return [Evidence("polyline_shape_sheet_points", int(len(sheet_pts)), "deterministic", "geometry",
                         note=f"need >= {min_points} traced points on {sheet_layer.name}")]

    bbox = _bounds(ref_layer.data)
    bbox = (bbox[0] - pad_m, bbox[1] - pad_m, bbox[2] + pad_m, bbox[3] + pad_m)
    dist_px, W, H = _rasterize(ref_layer.data, bbox, res_m)
    import cv2
    dist_m = cv2.distanceTransform((dist_px == 0).astype(np.uint8), cv2.DIST_L2, 3) * res_m
    off_grid_m = max(bbox[2] - bbox[0], bbox[3] - bbox[1])

    pts_crs = _apply(h.transform, sheet_pts)
    dist = _chamfer(dist_m, bbox, res_m, pts_crs, off_grid_m)

    inliers = dist <= outlier_tol_m
    n_total, n_in = len(dist), int(inliers.sum())
    matched_fraction = float(np.mean(dist[inliers] <= tol_m)) if n_in else 0.0
    fitted_mean = float(np.mean(dist[inliers])) if n_in else float(off_grid_m)
    outlier_fraction = 1.0 - n_in / n_total if n_total else 1.0

    # chance level: the same points shifted a few hundred metres in each cardinal direction; the easiest of those
    # wrong poses must still score worse than the fit by a clear margin, or the match is meaningless.
    shifts = [(shift_m, 0.0), (-shift_m, 0.0), (0.0, shift_m), (0.0, -shift_m)]
    chance_means = []
    for dx, dy in shifts:
        d = _chamfer(dist_m, bbox, res_m, pts_crs + np.array([dx, dy]), off_grid_m)
        inl = d <= outlier_tol_m
        chance_means.append(float(np.mean(d[inl])) if inl.any() else float(off_grid_m))
    chance_mean = min(chance_means)
    margin_ok = bool(fitted_mean <= chance_mean - margin_m)

    sinuosity = _sinuosity(ref_layer.data)
    curvature_ok = bool(sinuosity >= min_sinuosity)

    return [
        Evidence("polyline_shape_matched_fraction", round(matched_fraction, 4), "deterministic", "geometry",
                note=f"{n_in}/{n_total} points inlying (outlier tol {outlier_tol_m} m), tol {tol_m} m; "
                     f"outlier (reclaimed) fraction {outlier_fraction:.3f}; matcher {h.matcher}"),
        Evidence("polyline_shape_chamfer_mean_m", round(fitted_mean, 2), "deterministic", "geometry",
                note=f"mean chamfer distance of inlying points, res {res_m} m/px"),
        Evidence("polyline_shape_chance_margin_ok", margin_ok, "deterministic", "geometry",
                note=f"fitted {fitted_mean:.1f} m vs best-of-shifts chance {chance_mean:.1f} m "
                     f"(shift {shift_m} m), required margin {margin_m} m"),
        Evidence("polyline_shape_has_curvature", curvature_ok, "deterministic", "geometry",
                note=f"sinuosity {sinuosity:.3f} (>= {min_sinuosity} required; a straight line matches everywhere)"),
    ]


register(Primitive("polyline_shape_match", "geometry", True, ("layer", "hypothesis"), "evidence",
                   "chamfer-match the sheet's land/water boundary (or any traced linework) against a reference "
                   "polyline layer's distance transform under the fitted hypothesis's transform; matched fraction "
                   "after clipping reclaimed stretches as outliers, scored against a shifted chance level",
                   polyline_shape_match, "generated", requires=("opencv", "shapely")))
