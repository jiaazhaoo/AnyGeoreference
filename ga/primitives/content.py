"""Content against the world: the sheet's own drawing (its water, its dark line work) matched to OpenStreetMap's water and
roads, patch by patch, through a placement. Each patch that correlates is a control measurement (where this part of
the sheet really is); a robust similarity through them is a placement made from content, and the patches left out of
each fit test it out of sample. Names say roughly where; content says exactly where and whether.

Sheet layers (colour relative to the sheet's own paper, so yellowed paper and faded ink are handled alike):
  water  the blue plate (basemap.water_mask)
  dark   black line work: dark and colourless pixels (roads, tracks, buildings, rail; also lettering, which the
         reference has no counterpart for and so only adds noise)
Reference layers, from the pinned OpenFreeMap vector tiles (the same source as the water check):
  water  water areas (outlined) and waterways
  roads  every road, track and path class in the transportation layer, and railways
"""
from __future__ import annotations

import math

import numpy as np


def dark_mask(rgb: np.ndarray, rel: float = 0.55, max_chroma: int = 70) -> np.ndarray:
    """Black line work relative to the paper: much darker than the paper and without colour."""
    a = rgb.astype(np.int16)
    gray = a.mean(-1)
    paper = float(np.percentile(gray, 80))
    chroma = a.max(-1) - a.min(-1)
    return (gray < rel * paper) & (chroma < max_chroma)


def sheet_layers(rgb: np.ndarray) -> dict:
    import cv2
    from .basemap import water_mask
    w = water_mask(rgb).astype(np.uint8)
    w = cv2.morphologyEx(w, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))          # areas -> outlines, like OSM's
    return {"water": w, "dark": dark_mask(rgb).astype(np.uint8)}


def osm_layers(south: float, west: float, north: float, east: float, z: int = 13) -> dict:
    """{'water': (polygons, lines), 'roads': lines} in WGS84 lon/lat from the pinned vector tiles."""
    import mapbox_vector_tile
    from concurrent.futures import ThreadPoolExecutor
    from .basemap import _fetch_tile, _tile_range
    xs, ys = _tile_range(south, west, north, east, z)
    keys = [(x, y) for x in xs for y in ys]
    with ThreadPoolExecutor(4) as ex:
        blobs = list(ex.map(lambda k: _fetch_tile(z, *k), keys))
    n = 2 ** z

    def ll(x, y, coords, ext):
        c = np.asarray(coords, float)
        px, py = (x + c[:, 0] / ext) / n, (y + c[:, 1] / ext) / n
        return np.c_[px * 360 - 180, np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * py))))]

    polys, wlines, roads = [], [], []
    for (x, y), blob in zip(keys, blobs):
        if not blob:
            continue
        d = mapbox_vector_tile.decode(blob, default_options={"y_coord_down": True})
        for f in d.get("water", {}).get("features", []):
            g, ext = f["geometry"], d["water"].get("extent", 4096)
            parts = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"] if g["type"] == "MultiPolygon" else []
            for poly in parts:
                polys.append([ll(x, y, ring, ext) for ring in poly if len(ring) >= 3])
        for layer, out in (("waterway", wlines), ("transportation", roads)):
            L = d.get(layer)
            if not L:
                continue
            ext = L.get("extent", 4096)
            for f in L["features"]:
                g = f["geometry"]
                parts = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"] if g["type"] == "MultiLineString" else []
                for ln in parts:
                    if len(ln) >= 2:
                        out.append(ll(x, y, ln, ext))
    return {"water": (polys, wlines), "roads": roads}


def render(lines_polys: dict, lons: np.ndarray, lats: np.ndarray, shape) -> dict:
    """Reference layers drawn on the sheet's lon/lat grid (same frame as graticule.warp_to_grid)."""
    import cv2
    dlon, dlat = lons[1] - lons[0], lats[0] - lats[1]

    def to_px(c):
        return np.round(np.c_[(c[:, 0] - lons[0]) / dlon, (lats[0] - c[:, 1]) / dlat]).astype(np.int32)

    polys, wlines = lines_polys["water"]
    area = np.zeros(shape, np.uint8)
    for rings in polys:
        cv2.fillPoly(area, [to_px(r) for r in rings], 1)
    water = cv2.morphologyEx(area, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) * 255
    for ln in wlines:
        cv2.polylines(water, [to_px(ln)], False, 255, 2)
    roads = np.zeros(shape, np.uint8)
    for ln in lines_polys["roads"]:
        cv2.polylines(roads, [to_px(ln)], False, 255, 2)
    return {"water": water, "roads": roads}


PAIRS = (("water", "water"), ("dark", "roads"))          # sheet layer -> reference layer


def grids(rgb: np.ndarray, coeffs: np.ndarray, model: str, bounds, pad_deg: float, res_m: float = 20.0):
    """The sheet's layers resampled through the placement onto a lon/lat grid over bounds widened by pad_deg, and the
    reference rendered on the same grid. Returns (sheet layers, reference layers, covered, lons, lats)."""
    from .graticule import warp_to_grid
    west, south, east, north = bounds
    big = (west - pad_deg, south - pad_deg, east + pad_deg, north + pad_deg)
    sl = sheet_layers(rgb)
    out, covered, lons, lats = {}, None, None, None
    for name, m in sl.items():
        img, covered, (lons, lats) = warp_to_grid(255 - m * 255, coeffs, model, big, res_m)
        out[name] = img.astype(np.float32)
    ref = render(osm_layers(big[1], big[0], big[3], big[2]), lons, lats, out["water"].shape)
    return out, {k: v.astype(np.float32) for k, v in ref.items()}, covered, lons, lats


def correlate(a: np.ndarray, b: np.ndarray, mask: np.ndarray | None = None, min_ink: float = 0.002):
    """Phase correlation of sheet layer a against reference layer b (both blurred a little). Returns (dx, dy, response)
    in grid pixels (the reference is this far right / down of the sheet), or None when either has too little ink."""
    import cv2
    if mask is not None and mask.any():
        if float((a > 40)[mask].mean()) < min_ink:
            return None
    elif float((a > 40).mean()) < min_ink:
        return None
    if float((b > 40).mean()) < min_ink:
        return None
    a = cv2.GaussianBlur(a, (0, 0), 1.5)
    b = cv2.GaussianBlur(b, (0, 0), 1.5)
    win = cv2.createHanningWindow((a.shape[1], a.shape[0]), cv2.CV_32F)
    (dx, dy), resp = cv2.phaseCorrelate(np.ascontiguousarray(a), np.ascontiguousarray(b), win)
    return float(dx), float(dy), float(resp)


def patch_measurements(sheet: dict, ref: dict, covered: np.ndarray, n: int = 4, pad_px: int = 0):
    """Each layer pair, in an n x n grid of patches over the sheet's covered area (each patch widened by pad_px so a
    shift up to that size stays inside): (layer, patch centre (col, row), dx, dy, response)."""
    rows, cols = np.nonzero(covered)
    if not len(rows):
        return []
    r0, r1, c0, c1 = rows.min(), rows.max(), cols.min(), cols.max()
    H, W = covered.shape
    out = []
    for i in range(n):
        for j in range(n):
            ra, rb = r0 + (r1 - r0) * i // n, r0 + (r1 - r0) * (i + 1) // n
            ca, cb = c0 + (c1 - c0) * j // n, c0 + (c1 - c0) * (j + 1) // n
            sl = (slice(max(0, ra - pad_px), min(H, rb + pad_px)), slice(max(0, ca - pad_px), min(W, cb + pad_px)))
            for s_name, r_name in PAIRS:
                c = correlate(sheet[s_name][sl], ref[r_name][sl], covered[sl])
                if c:
                    out.append((s_name, ((ca + cb) / 2.0, (ra + rb) / 2.0), *c))
    return out


def deg_per_m(lat: float) -> tuple[float, float]:
    return 1.0 / (111320.0 * math.cos(math.radians(lat))), 1.0 / 110574.0


def combined(layers: dict, names) -> np.ndarray:
    return np.clip(sum(layers[n] for n in names), 0, 255).astype(np.float32)


def window_measurements(sheet: dict, ref: dict, covered: np.ndarray, k: int = 3, frac: float = 0.5):
    """Overlapping windows, each frac of the covered area's width and height, on a k x k lattice; in each, the
    sheet's water + dark line work against OSM's water + roads. Returns (centre (col, row), dx, dy, response)."""
    rows, cols = np.nonzero(covered)
    if not len(rows):
        return []
    r0, r1, c0, c1 = rows.min(), rows.max(), cols.min(), cols.max()
    hh, ww = int((r1 - r0) * frac), int((c1 - c0) * frac)
    a, b = combined(sheet, ("water", "dark")), combined(ref, ("water", "roads"))
    out = []
    for i in range(k):
        for j in range(k):
            ra = r0 + int((r1 - r0 - hh) * i / max(1, k - 1))
            ca = c0 + int((c1 - c0 - ww) * j / max(1, k - 1))
            sl = (slice(ra, ra + hh), slice(ca, ca + ww))
            c = correlate(a[sl], b[sl], covered[sl])
            if c:
                out.append(((ca + ww / 2.0, ra + hh / 2.0), *c))
    return out


def match(a: np.ndarray, b: np.ndarray, sl, search_px: int, min_ink: float = 0.004, blur: float = 1.5, exclude_px: int = 4):
    """Normalised cross-correlation of the sheet window a[sl] against the reference b around the same place, up to
    search_px either way. Phase correlation was tried first: on windows smaller than the sheet it often locked onto
    zero shift (broad dark areas and lettering carry low-frequency energy both images share by position).
    Returns (dx, dy, score, distinct): the reference is dx right, dy down of the sheet; score is the peak NCC and
    distinct how far it stands above the best peak farther than exclude_px away. None with too little ink."""
    import cv2
    ra, rb = sl[0].start, sl[0].stop
    ca, cb = sl[1].start, sl[1].stop
    H, W = b.shape
    if ra - search_px < 0 or ca - search_px < 0 or rb + search_px > H or cb + search_px > W:
        return None
    t = a[ra:rb, ca:cb]
    s = b[ra - search_px:rb + search_px, ca - search_px:cb + search_px]
    if float((t > 40).mean()) < min_ink or float((s > 40).mean()) < min_ink:
        return None
    t = cv2.GaussianBlur(t, (0, 0), blur)
    s = cv2.GaussianBlur(s, (0, 0), blur)
    m = cv2.matchTemplate(s, t, cv2.TM_CCOEFF_NORMED)
    _, peak, _, (px, py) = cv2.minMaxLoc(m)
    m2 = m.copy()
    m2[max(0, py - exclude_px):py + exclude_px + 1, max(0, px - exclude_px):px + exclude_px + 1] = -1
    second = float(m2.max())

    def sub(l, c, r):                                    # parabola through the peak and its neighbours
        d = l - 2 * c + r
        return 0.0 if d >= 0 else max(-0.5, min(0.5, 0.5 * (l - r) / d))
    fx = sub(m[py, px - 1], peak, m[py, px + 1]) if 0 < px < m.shape[1] - 1 else 0.0
    fy = sub(m[py - 1, px], peak, m[py + 1, px]) if 0 < py < m.shape[0] - 1 else 0.0
    return float(px + fx - search_px), float(py + fy - search_px), float(peak), float(peak - second)


def window_matches(sheet: dict, ref: dict, covered: np.ndarray, search_px: int, k: int = 3, frac: float = 0.5):
    """match() on overlapping windows (frac of the sheet's covered extent, k x k lattice) and on the whole sheet.
    Returns [(centre (col, row), dx, dy, score, distinct, is_whole)]."""
    rows, cols = np.nonzero(covered)
    if not len(rows):
        return []
    r0, r1, c0, c1 = int(rows.min()), int(rows.max()), int(cols.min()), int(cols.max())
    a, b = combined(sheet, ("water", "dark")), combined(ref, ("water", "roads"))
    out = []
    c = match(a, b, (slice(r0, r1), slice(c0, c1)), search_px)
    if c:
        out.append((((c0 + c1) / 2.0, (r0 + r1) / 2.0), *c, True))
    hh, ww = int((r1 - r0) * frac), int((c1 - c0) * frac)
    for i in range(k):
        for j in range(k):
            ra = r0 + int((r1 - r0 - hh) * i / max(1, k - 1))
            ca = c0 + int((c1 - c0 - ww) * j / max(1, k - 1))
            c = match(a, b, (slice(ra, ra + hh), slice(ca, ca + ww)), search_px)
            if c:
                out.append(((ca + ww / 2.0, ra + hh / 2.0), *c, False))
    return out


# -- the primitive: a placement from content, tested out of sample ---------------------------------------------------
def _sim_fit(src: np.ndarray, dst: np.ndarray):
    """Least-squares similarity dst = m * src + t on complex numbers (east + i north, metres)."""
    A = np.c_[src, np.ones(len(src))]
    m, t = np.linalg.lstsq(A, dst, rcond=None)[0]
    return m, t


def _aff_fit(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Least-squares affine (2 x 3) from complex src to complex dst."""
    A = np.c_[src.real, src.imag, np.ones(len(src))]
    return np.linalg.lstsq(A, np.c_[dst.real, dst.imag], rcond=None)[0].T


def _loo(src: np.ndarray, dst: np.ndarray, idx: list, model: str) -> list:
    """Leave-one-out errors (m) of each measurement in idx, predicted by the model fitted on the others."""
    need = 2 if model == "similarity" else 3
    out = []
    for i in idx:
        o = [j for j in idx if j != i]
        if len(o) < need:
            continue
        if model == "similarity":
            m_, t_ = _sim_fit(src[o], dst[o])
            out.append(float(abs(m_ * src[i] + t_ - dst[i])))
        else:
            P = _aff_fit(src[o], dst[o])
            q = P @ np.array([src[i].real, src[i].imag, 1.0])
            out.append(float(abs(complex(q[0], q[1]) - dst[i])))
    return out


def _robust(src: np.ndarray, dst: np.ndarray, tol_m: float):
    """RANSAC over pairs, then least squares on the inliers. Returns (m, t, inlier mask) or None."""
    n = len(src)
    if n < 3:
        return None
    best = None
    for i in range(n):
        for j in range(i + 1, n):
            if abs(src[j] - src[i]) < 1e-6:
                continue
            m = (dst[j] - dst[i]) / (src[j] - src[i])
            if not (0.8 <= abs(m) <= 1.25) or abs(math.degrees(np.angle(m))) > 10:
                continue
            t = dst[i] - m * src[i]
            r = np.abs(m * src + t - dst)
            mask = r <= tol_m
            key = (int(mask.sum()), -float(r[mask].sum()))
            if best is None or key > best[0]:
                best = (key, mask)
    if best is None or best[0][0] < 3:
        return None
    mask = best[1]
    for _ in range(3):
        m, t = _sim_fit(src[mask], dst[mask])
        new = np.abs(m * src + t - dst) <= tol_m
        if new.sum() < 3 or (new == mask).all():
            break
        mask = new
    m, t = _sim_fit(src[mask], dst[mask])
    return m, t, mask


def content_fit(state, res_m: float = 20.0, pad_deg: float = 0.025, search_m=(1000.0, 200.0, 100.0), tol_m: float = 40.0,
                min_distinct: float = 0.01, max_move_rms: float = 4.0, k: int = 3, min_affine: int = 6):
    """Move the best placement onto the sheet's content: its water and dark line work against OpenStreetMap's water
    and roads (pinned vector tiles), by normalised cross-correlation in overlapping windows (half the sheet each, a
    k x k lattice) and over the whole sheet. Each window that correlates is a control measurement; a robust
    similarity through them corrects shift, scale and rotation; repeated with a narrower search. Then every inlier
    window is left out in turn, the similarity refitted on the others, and its own measurement predicted: the
    out-of-sample error. The moved placement goes first (inserted directly; the primitive returns evidence).
    Evidence: content_windows (inlier windows), content_rows_cols (distinct lattice rows and columns they span),
    content_loo_m (worst leave-one-out error), content_moved_m, content_within_names (the move is within the names'
    own uncertainty)."""
    from evalcore import Evidence
    from pyproj import Transformer
    from .basemap import rgb_of
    from .names_world import _lonlat_fit
    from ..model import Hypothesis
    if not state.hypotheses:
        return []
    h0 = state.hypotheses[0]
    W, H = state.sheet.meta.get("width", 0), state.sheet.meta.get("height", 0)
    rgb = rgb_of(state.sheet.image)
    to_ll = Transformer.from_crs(h0.crs, "EPSG:4326", always_xy=True)
    to_xy = Transformer.from_crs("EPSG:4326", h0.crs, always_xy=True)
    M = complex(h0.transform[0], h0.transform[1])
    tau = complex(h0.transform[2], h0.transform[5])
    centre = complex(W / 2, -H / 2)
    c0 = M * centre + tau
    last = None
    for search in search_m:
        T6 = (M.real, M.imag, tau.real, M.imag, -M.real, tau.imag)
        coeffs, bounds = _lonlat_fit(Hypothesis(h0.sheet, T6, h0.site_wkt, h0.crs, h0.score, h0.matcher), W, H)
        try:
            sheet, ref, cov, lons, lats = grids(rgb, coeffs, "poly2", bounds, pad_deg, res_m)
        except Exception as e:                                         # noqa: BLE001  tiles unreachable
            return [Evidence("content_windows", None, "deterministic", "basemap", note=str(e)[:160])]
        ms = [x for x in window_matches(sheet, ref, cov, int(search / res_m), k=k) if x[4] >= min_distinct]
        if len(ms) < 3:
            last = None
            break
        dlon, dlat = lons[1] - lons[0], lats[0] - lats[1]
        lo = np.array([lons[0] + x[0][0] * dlon for x in ms]); la = np.array([lats[0] - x[0][1] * dlat for x in ms])
        lo2 = lo + np.array([x[1] for x in ms]) * dlon; la2 = la - np.array([x[2] for x in ms]) * dlat
        sx, sy = to_xy.transform(lo, la); tx, ty = to_xy.transform(lo2, la2)
        src, dst = np.asarray(sx) + 1j * np.asarray(sy), np.asarray(tx) + 1j * np.asarray(ty)
        fit = _robust(src, dst, max(tol_m, 2 * res_m))
        if fit is None:
            last = None
            break
        mc, tc, mask = fit
        prev = (M, tau)
        M, tau = mc * M, mc * tau + tc
        last = (ms, src, dst, mask, mc, tc, prev)
    if last is None:
        return [Evidence("content_windows", 0, "deterministic", "basemap", note="fewer than three windows correlate, or they do not agree")]
    ms, src, dst, mask, mc, tc, prev = last
    # out of sample: each inlier window predicted from the others (measured in the last round's frame), for a
    # similarity and for an affine (old sheets are sheared and stretched inside); the model that predicts better wins
    idx = [i for i in range(len(ms)) if mask[i] and not ms[i][5]]
    loo = _loo(src, dst, idx, "similarity")
    model, T_aff = "similarity", None
    if len(idx) >= min_affine:
        loo_a = _loo(src, dst, idx, "affine")
        if loo_a and loo and max(loo_a) < max(loo):
            loo, model = loo_a, "affine"
            P = _aff_fit(src[mask], dst[mask])                      # [X', Y'] = P @ [X, Y, 1] on the previous frame
            Mp, tp = prev
            A = np.array([[Mp.real, Mp.imag, tp.real], [Mp.imag, -Mp.real, tp.imag], [0, 0, 1.0]])
            N = np.vstack([P, [0, 0, 1.0]]) @ A
            T_aff = tuple(float(v) for v in (*N[0], *N[1]))
    win = [ms[i] for i in idx]
    rc = (len({round(w[0][1]) for w in win}), len({round(w[0][0]) for w in win}))
    moved = abs((M * centre + tau) - c0)
    rms_px = next((e.value for e in reversed(state.evidence) if e.name == "names_rms_px"), None)
    reach = max_move_rms * float(rms_px) * abs(complex(h0.transform[0], h0.transform[1])) if rms_px else float("inf")
    within = bool(moved <= reach)
    T6 = (float(M.real), float(M.imag), float(tau.real), float(M.imag), float(-M.real), float(tau.imag))
    if T_aff is not None:
        T6 = T_aff
        moved = abs(complex(T6[0] * W / 2 + T6[1] * H / 2 + T6[2], T6[3] * W / 2 + T6[4] * H / 2 + T6[5]) - c0)
        within = bool(moved <= reach)
    corners = [(0, 0), (W, 0), (W, H), (0, H), (0, 0)]
    wkt = "POLYGON((" + ",".join(f"{T6[0]*x + T6[1]*y + T6[2]:.2f} {T6[3]*x + T6[4]*y + T6[5]:.2f}" for x, y in corners) + "))"
    # the names' scatter does not bound their bias (a placement 840 m off had labels within 100 m of their features),
    # so the move is kept and the comparison left to the policy as a fact
    if True:
        state.hypotheses.insert(0, Hypothesis(h0.sheet, T6, wkt, h0.crs, h0.score, f"{h0.matcher}+content", h0.candidates,
                                              note=f"{h0.note}; moved {moved:.0f} m onto water and roads"))
    loo_max = round(max(loo), 1) if loo else None
    state.evidence.append(Evidence("content_model", model, "deterministic", "basemap"))
    return [Evidence("content_windows", len(idx), "deterministic", "basemap",
                     note=f"{len(idx)} of {len(ms)} windows agree (of {k * k} + whole); rows x cols {rc}; last correction x{abs(mc):.4f}, {math.degrees(np.angle(mc)):+.2f} deg, {abs(tc):.0f} m"),
            Evidence("content_rows_cols", min(rc), "deterministic", "basemap"),
            Evidence("content_loo_m", loo_max, "deterministic", "basemap", note=f"leave-one-out errors {[round(x) for x in loo]}"),
            Evidence("content_moved_m", round(float(moved), 1), "deterministic", "basemap"),
            Evidence("content_within_names", within, "deterministic", "basemap", note=f"moved {moved:.0f} m; names allow {reach:.0f} m")]


def _register():
    from . import Primitive, register
    register(Primitive("content_fit", "basemap", True, ("hypothesis",), "evidence",
                       "the placement moved onto the sheet's water and dark line work matched to OpenStreetMap water and roads in overlapping windows "
                       "(robust similarity), with a leave-one-window-out error", content_fit, "generic", requires=("opencv", "network: OSM vector tiles")))


_register()
