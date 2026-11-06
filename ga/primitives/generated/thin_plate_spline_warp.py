"""thin_plate_spline_warp: the sketch family's deliverable. toponym_constellation_fit (or any gazetteer matcher)
finds a similarity transform and the named points it trusts; this primitive takes those matched point pairs
(sheet pixel, gazetteer ground position) as the control points of a thin plate spline and warps the sheet's named
positions (and, when the sheet image is on disk, the raster itself) through them for DISPLAY, not measurement.
TPS minimises bending energy subject to exact interpolation at the controls, using the standard kernel
U(r) = r^2 log r. Outside the convex hull of the controls (plus a small margin) nothing is warped: a rubber sheet
does not know what lies past its pins. The output is tagged 'schematic, not for measurement' and carries, as its
distortion score, the RMS residual of a similarity fit through the very same control points -- the measure of how
schematic the sheet is, per knowledge base family-sketch-and-schematic."""
from __future__ import annotations

import math
import os
import sqlite3

import numpy as np

from .. import Primitive, register
from ..generic import fit_transform
from ...model import Layer

DEFAULT_DB = "/data/reference/base-data/opname_csv_gb/os_open_names_uk.sqlite"


# -- thin plate spline: fit two scalar TPS (one per target dim) through src -> dst control points ------------------
def _tps_fit(src: np.ndarray, dst: np.ndarray, reg: float = 0.0) -> np.ndarray:
    n = len(src)
    r = np.linalg.norm(src[:, None, :] - src[None, :, :], axis=2)
    with np.errstate(divide="ignore", invalid="ignore"):
        K = np.where(r > 0, r * r * np.log(r), 0.0)
    if reg:
        K = K + reg * np.eye(n)
    P = np.c_[np.ones(n), src]                              # n x 3: [1, x, y]
    L = np.zeros((n + 3, n + 3))
    L[:n, :n] = K
    L[:n, n:] = P
    L[n:, :n] = P.T
    Y = np.zeros((n + 3, 2))
    Y[:n] = dst
    try:
        W = np.linalg.solve(L, Y)
    except np.linalg.LinAlgError:
        W = np.linalg.lstsq(L, Y, rcond=None)[0]
    return W                                                 # rows [0:n] = per-control weights, [n:n+3] = affine


def _tps_apply(W: np.ndarray, src: np.ndarray, query: np.ndarray) -> np.ndarray:
    n = len(src)
    w, aff = W[:n], W[n:]
    r = np.linalg.norm(query[:, None, :] - src[None, :, :], axis=2)
    with np.errstate(divide="ignore", invalid="ignore"):
        U = np.where(r > 0, r * r * np.log(r), 0.0)
    return np.c_[np.ones(len(query)), query] @ aff + U @ w


# -- matched point pairs: reproject named cues with the matcher's transform, keep the gazetteer hit it lands near --
def _sheet_name_points(state, name_kinds, min_text_len):
    groups: dict[str, list] = {}
    for c in state.cues:
        if c.kind not in name_kinds:
            continue
        t = c.text.strip()
        if len(t) < min_text_len:
            continue
        x0, y0, x1, y1 = c.bbox
        groups.setdefault(t.lower(), []).append((t, (x0 + x1) / 2.0, (y0 + y1) / 2.0))
    out = {}
    for items in groups.values():
        name = items[0][0]
        out[name] = (sum(i[1] for i in items) / len(items), sum(i[2] for i in items) / len(items))
    return out


def _gazetteer_hits(db, names, bbox):
    x0, y0, x1, y1 = bbox
    con = sqlite3.connect(db)
    out = {}
    try:
        for name in names:
            rows = con.execute(
                "SELECT GEOMETRY_X, GEOMETRY_Y FROM open_names WHERE NAME1 = ? COLLATE NOCASE "
                "AND GEOMETRY_X BETWEEN ? AND ? AND GEOMETRY_Y BETWEEN ? AND ?",
                (name, x0, x1, y0, y1)).fetchall()
            if rows:
                out[name] = [(float(r[0]), float(r[1])) for r in rows]
    finally:
        con.close()
    return out


def thin_plate_spline_warp(state, matcher_name: str = "toponym_constellation_fit", name_kinds=("place", "landmark"),
                           min_text_len: int = 3, inlier_tol_m: float = 250.0, min_control: int = 3,
                           hull_margin_frac: float = 0.25, db: str | None = None, regularization: float = 0.0,
                           warp_raster: bool = True, max_raster_dim: int = 1200):
    """Build the TPS from toponym_constellation_fit's inlier pairs and warp the named label positions (and the
    sheet raster, when it is readable) into the gazetteer CRS for display. Abstains (returns []) below
    min_control matched points, exactly like the matcher it rides on."""
    if not state.hypotheses or not state.candidates:
        return []
    h = next((x for x in state.hypotheses if x.matcher == matcher_name), state.hypotheses[0])
    cand = next((c for c in state.candidates if c.source == "gazetteer"), state.candidates[0])

    import shapely.wkt
    area = shapely.wkt.loads(cand.area_wkt)
    if area.is_empty:
        return []
    bbox = area.bounds

    sheet_points = _sheet_name_points(state, name_kinds, min_text_len)
    if len(sheet_points) < min_control:
        return []
    db = db or os.environ.get("E2E_OPEN_NAMES", DEFAULT_DB)
    try:
        gaz = _gazetteer_hits(db, sheet_points, bbox)
    except sqlite3.Error:
        return []
    if len(gaz) < min_control:
        return []

    a, b, c_, d, e, f = h.transform                          # the matcher's similarity: sheet px -> CRS

    src, dst, used = [], [], []
    for name, (px, py) in sheet_points.items():
        hits = gaz.get(name)
        if not hits:
            continue
        gx, gy = a * px + b * py + c_, d * px + e * py + f
        bx, by = min(hits, key=lambda p: math.hypot(p[0] - gx, p[1] - gy))
        if math.hypot(bx - gx, by - gy) <= inlier_tol_m:
            src.append((px, py)); dst.append((bx, by)); used.append(name)
    if len(src) < min_control:
        return []
    src_a, dst_a = np.array(src, float), np.array(dst, float)

    sim_coeffs, sim_res = fit_transform(src_a, dst_a, "similarity")
    distortion_rms_m = float(np.sqrt(np.mean(sim_res ** 2))) if len(sim_res) else 0.0

    W = _tps_fit(src_a, dst_a, reg=regularization)

    from shapely.geometry import MultiPoint, Point
    hull = MultiPoint(src_a.tolist()).convex_hull
    hx0, hy0, hx1, hy1 = hull.bounds if not hull.is_empty else (src_a[:, 0].min(), src_a[:, 1].min(), src_a[:, 0].max(), src_a[:, 1].max())
    margin = hull_margin_frac * max(hx1 - hx0, hy1 - hy0, 1.0)
    allowed = hull.buffer(margin)

    points = []
    for name, (px, py) in sheet_points.items():
        if not allowed.contains(Point(px, py)):
            continue
        wx, wy = _tps_apply(W, src_a, np.array([[px, py]], float))[0]
        points.append({"name": name, "sheet_xy": (px, py), "warped_xy": (float(wx), float(wy)),
                       "is_control": name in used})

    note = f"schematic, not for measurement; {len(used)} control points; similarity-fit rms {distortion_rms_m:.1f} m"
    meta = {"tag": "schematic, not for measurement", "distortion_score_m": distortion_rms_m,
            "n_control_points": len(used), "control_points": list(zip(src, dst)), "matcher": h.matcher,
            "crs": cand.crs, "model": "thin_plate_spline", "kernel": "r^2 log r", "note": note}
    out = [Layer(state.sheet.digest, "tps_warped_labels", "points", points, frame=cand.crs, meta=meta)]

    if warp_raster and os.path.isfile(state.sheet.image):
        try:
            import cv2
            img = cv2.imread(state.sheet.image)
        except Exception:                                    # noqa: BLE001
            img = None
        if img is not None:
            scale = math.sqrt(abs(a * e - b * d)) or 1.0      # metres per sheet pixel, from the similarity fit
            ox0, oy0, ox1, oy1 = allowed.bounds
            # ground-space bbox the warped controls can fill; buffered hull mapped forward, pixel size ~ scale
            gxy = _tps_apply(W, src_a, np.array([[ox0, oy0], [ox1, oy0], [ox1, oy1], [ox0, oy1]], float))
            gx0, gy0 = gxy[:, 0].min(), gxy[:, 1].min()
            gx1, gy1 = gxy[:, 0].max(), gxy[:, 1].max()
            W_out = max(1, min(max_raster_dim, int(round((gx1 - gx0) / scale))))
            H_out = max(1, min(max_raster_dim, int(round((gy1 - gy0) / scale))))
            W_inv = _tps_fit(dst_a, src_a, reg=regularization)   # ground xy -> sheet px, for sampling
            gx = gx0 + (np.arange(W_out) + 0.5) * (gx1 - gx0) / W_out
            gy = gy1 - (np.arange(H_out) + 0.5) * (gy1 - gy0) / H_out
            gxx, gyy = np.meshgrid(gx, gy)
            query = np.c_[gxx.ravel(), gyy.ravel()]
            src_px = _tps_apply(W_inv, dst_a, query)
            map_x = src_px[:, 0].reshape(H_out, W_out).astype(np.float32)
            map_y = src_px[:, 1].reshape(H_out, W_out).astype(np.float32)
            warped = cv2.remap(img, map_x, map_y, cv2.INTER_LINEAR, borderValue=0)
            out.append(Layer(state.sheet.digest, "tps_warped_raster", "raster", warped, frame=cand.crs,
                             meta={**meta, "bbox": (float(gx0), float(gy0), float(gx1), float(gy1)),
                                   "res_m": scale}))
    return out


register(Primitive("thin_plate_spline_warp", "gazetteer", True, ("hypothesis", "candidate"), "layer",
                   "thin plate spline through toponym_constellation_fit's matched (sheet px, gazetteer xy) inlier "
                   "pairs; warps named label positions (and the raster, if readable) for display, tagged "
                   "'schematic, not for measurement' with the similarity-fit RMS as its distortion score",
                   thin_plate_spline_warp, "generated", requires=("OS Open Names",)))
