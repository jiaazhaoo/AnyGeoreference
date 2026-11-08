"""Generic primitives for survey sheets with a printed graticule: read the lines, check one edition against another.
OpenCV and numpy only; no sheet index, no learned model, no reference data.

`graticule_lines` finds the meridians and parallels a survey prints across the map (the neatline is the outermost
pair) and returns every intersection as a grid cue carrying its printed lon/lat. The neatline bounds and the
graticule interval are facts of the sheet: the record supplies them (printed at the corners) or a reader does.

`edition_agreement` is the second family for a sheet placed from its own graticule. A small residual at the
graticule nodes proves the fit is self-consistent, not that the lines were read right: a reader that takes the
wrong family of lines keeps a small residual and lands one interval away. Another edition or printing of the same
sheet, placed on its own, is resampled with this one onto a common lon/lat grid through each scan's own placement,
the graticule masked out (it agrees by construction), and the remaining map content (coast, roads, contours) must
line up with no shift. Editions re-drawn years apart share no feature points but still share their coastline."""
from __future__ import annotations

import ast
import math

import numpy as np

from ..model import Cue, Layer
from . import Primitive, register
from evalcore import Evidence


# -- reading ---------------------------------------------------------------------------------------------------------
def gray_of(path: str) -> np.ndarray:
    """Grey pixels of a sheet. A GeoTIFF is read as pixels only: its georeference is never used here."""
    import cv2
    if path.lower().endswith((".tif", ".tiff")):
        import rasterio
        with rasterio.open(path) as ds:
            arr = ds.read([1, 2, 3]) if ds.count >= 3 else np.repeat(ds.read([1]), 3, axis=0)
        return cv2.cvtColor(np.ascontiguousarray(arr.transpose(1, 2, 0)), cv2.COLOR_RGB2GRAY)
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(path)
    return img


def ridge_mask(gray: np.ndarray, axis: str, offset: int = 3, contrast: int = 25) -> np.ndarray:
    """Thin dark lines along one axis: a pixel darker by `contrast` than both pixels `offset` away across the line.
    Filled areas (water tint, dense type) are not ridges, so they do not compete with a hairline graticule."""
    g = gray.astype(np.int16)
    ax = 0 if axis == "h" else 1
    r = np.minimum(np.roll(g, offset, ax), np.roll(g, -offset, ax)) - g
    return (r > contrast).astype(np.float32)


def _strip_profiles(mask: np.ndarray, axis: str, n_strips: int):
    """Per-strip line profiles. For 'h' the profile runs down the rows of vertical strips; for 'v' the mask is
    transposed first, so both axes are handled as rows."""
    m = mask if axis == "h" else mask.T
    L, W = m.shape
    edges = np.linspace(0, W, n_strips + 1).astype(int)
    P = np.stack([m[:, edges[i]:edges[i + 1]].mean(1) for i in range(n_strips)])
    return P, (edges[:-1] + edges[1:]) / 2.0, L, W


def _shifted_sum(P, centres, W, slope):
    shifts = np.round((centres - W / 2) * slope).astype(int)
    return sum(np.roll(P[i], -shifts[i]) for i in range(len(P))) / len(P)


def find_lines(gray: np.ndarray, axis: str, n_strips: int = 24, max_slope: float = 0.02, min_strength: float = 0.2):
    """Long straight lines along one axis. Returns (lines, slope, ctx): each line is (position at mid-span, strength,
    own slope), strength being the share of the span on which the line is present; `slope` is the dominant one.
    Every line gets its own slope from a slope x position accumulator: meridians converge, so the two side neatlines
    of a sheet lean opposite ways, and one global skew smears whichever side it does not fit below the threshold."""
    mask = ridge_mask(gray, axis)
    P, centres, L, W = _strip_profiles(mask, axis, n_strips)
    slopes = np.linspace(-max_slope, max_slope, 201)
    A = np.stack([_shifted_sum(P, centres, W, s) for s in slopes])          # (slope, position)
    best_s = A.argmax(0)
    prof = A.max(0)
    dominant = float(slopes[int(np.argmax(np.sort(A, 1)[:, -16:].sum(1)))])
    prof = prof.copy()
    sep = max(8, int(0.01 * L))
    out = []
    while True:
        i = int(prof.argmax()); v = float(prof[i])
        if v < min_strength:
            break
        out.append((float(i), v, float(slopes[best_s[i]])))
        prof[max(0, i - sep):i + sep + 1] = 0
    return sorted(out), dominant, (P, centres, W)


def families(lines, n: int, length: int, min_interval: float = 0.08, tol: float = 0.012):
    """Every set of n+1 evenly spaced lines among `lines`: (mean strength, positions, spacing), best first. The two
    ends fix the spacing; each interior line must be found within `tol` of an interval of its expected place."""
    pos = np.array([ln[0] for ln in lines]); st = np.array([ln[1] for ln in lines])
    out = []
    for i in range(len(pos)):
        for j in range(i + 1, len(pos)):
            d = (pos[j] - pos[i]) / n
            if d < min_interval * length:
                continue
            idx = [i]
            for k in range(1, n):
                want = pos[i] + k * d
                m = int(np.argmin(np.abs(pos - want)))
                if abs(pos[m] - want) > max(3.0, tol * d):
                    break
                idx.append(m)
            else:
                idx.append(j)
                out.append((float(st[idx].mean()), [float(pos[x]) for x in idx], float(d), [float(st[x]) for x in idx]))
    return sorted(out, key=lambda f: -f[0])


def refine_line(P, centres, W, pos: float, slope: float, window: int = 6):
    """Position of one line strip by strip (sub-pixel peak near the predicted place), then a straight fit
    pos(t) = a t + b in the line's own direction; strips where the line is absent (type, a gap) are dropped."""
    ts, ps = [], []
    for k, c in enumerate(centres):
        guess = pos + (c - W / 2) * slope
        lo, hi = int(max(1, guess - window)), int(min(P.shape[1] - 2, guess + window))
        if hi <= lo:
            continue
        seg = P[k, lo:hi + 1]
        i = int(seg.argmax())
        if seg[i] < 0.3:
            continue
        j = lo + i
        y0, y1, y2 = P[k, j - 1], P[k, j], P[k, j + 1]
        den = y0 - 2 * y1 + y2
        ts.append(c); ps.append(j + (0.5 * (y0 - y2) / den if den != 0 else 0.0))
    if len(ts) < 4:
        return slope, pos - (W / 2) * slope, len(ts)
    ts, ps = np.array(ts), np.array(ps)
    a, b = np.polyfit(ts, ps, 1)
    r = np.abs(ps - (a * ts + b))
    keep = r <= max(1.5, 2.5 * np.median(r))
    if keep.sum() >= 4:
        a, b = np.polyfit(ts[keep], ps[keep], 1)
    return float(a), float(b), int(keep.sum())


def read_graticule(gray: np.ndarray, west: float, south: float, east: float, north: float, interval_min: float = 5.0,
                   pixel_space: str = "auto", ratio_tol: float = 0.03):
    """The graticule of one sheet: nodes (pixel, lon, lat), the chosen families and how clear the choice was.
    Returns None when no pair of families fits the printed bounds and interval."""
    step = interval_min / 60.0
    n_cols, n_rows = round((east - west) / step), round((north - south) / step)
    if n_cols < 1 or n_rows < 1:
        raise ValueError("bounds smaller than one graticule interval")
    lat0 = (north + south) / 2
    # spacing of meridians over spacing of parallels, in pixels: on paper (or a projected raster) a minute of
    # longitude is cos(lat) of a minute of latitude; a raster already resampled to degrees keeps them equal
    expected = {"paper": math.cos(math.radians(lat0)), "degrees": 1.0}
    spaces = [pixel_space] if pixel_space in expected else list(expected)
    H, W = gray.shape
    hl, hs, hctx = find_lines(gray, "h")
    vl, vs, vctx = find_lines(gray, "v")
    hf = families(hl, n_rows, H)[:8]
    vf = families(vl, n_cols, W)[:8]
    combos = []
    for space in spaces:
        for fh in hf:
            for fv in vf:
                r = fv[2] / fh[2]
                if abs(r / expected[space] - 1) <= ratio_tol:
                    combos.append((fh[0] + fv[0], fh, fv, space, r))
    if not combos:
        return {"found": False, "why": f"{len(hl)} horizontal and {len(vl)} vertical lines; {len(hf)} x {len(vf)} evenly spaced families; "
                                       f"none with the spacing ratio of a {interval_min}' graticule at {lat0:.2f} deg"}
    combos.sort(key=lambda c: -c[0])
    best = combos[0]
    rival = next((c for c in combos[1:] if c[1][1] != best[1][1] or c[2][1] != best[2][1]), None)
    _, fh, fv, space, ratio = best
    hsl = {ln[0]: ln[2] for ln in hl}; vsl = {ln[0]: ln[2] for ln in vl}
    hlines = [refine_line(*hctx, p, hsl.get(p, hs)) for p in fh[1]]          # y = a x + b
    vlines = [refine_line(*vctx, p, vsl.get(p, vs)) for p in fv[1]]          # x = c y + d
    nodes = []
    for j, (a, b, _) in enumerate(hlines):
        for i, (c, d, _) in enumerate(vlines):
            y = (a * d + b) / (1 - a * c)
            x = c * y + d
            nodes.append((x, y, west + i * step, north - j * step))
    return {"found": True, "nodes": nodes, "pixel_space": space, "spacing_ratio": ratio, "expected_ratio": expected[space],
            "strength": min(min(fh[3]), min(fv[3])), "score": best[0], "rival_score": rival[0] if rival else None,
            "rows": fh[1], "cols": fv[1], "corners": [(n[0], n[1]) for n in (nodes[0], nodes[n_cols], nodes[-1], nodes[-1 - n_cols])]}


def graticule_lines(state, interval_min: float = 5.0, ambiguity: float = 0.85):
    """Primitive: the record's neatline bounds [west, south, east, north] and the interval -> one grid cue per
    graticule node, a 'frame' layer, and evidence on how clear the reading was. No bounds -> nothing."""
    rec = {**dict(state.sheet.meta), **dict(state.sheet.record)}
    b = rec.get("bounds")
    if not b:
        return []
    west, south, east, north = (float(v) for v in b)
    interval_min = float(rec.get("interval_min", interval_min))
    g = read_graticule(gray_of(state.sheet.image), west, south, east, north, interval_min, rec.get("pixel_space", "auto"))
    if not g["found"]:
        state.evidence.append(Evidence("graticule_found", False, "deterministic", "sheet-reader", note=g["why"][:200]))
        return []
    rival = g["rival_score"]
    ambiguous = rival is not None and rival >= ambiguity * g["score"]
    state.evidence.append(Evidence("graticule_found", True, "deterministic", "sheet-reader",
                                   note=f"{len(g['nodes'])} nodes; weakest line on {g['strength']:.0%} of its span; spacing ratio {g['spacing_ratio']:.4f} "
                                        f"(expected {g['expected_ratio']:.4f}, {g['pixel_space']})"))
    state.evidence.append(Evidence("graticule_ambiguous", bool(ambiguous), "deterministic", "sheet-reader",
                                   note=f"best family {g['score']:.2f}, next {rival:.2f}" if rival is not None else "no rival family"))
    state.layers.append(Layer(state.sheet.digest, "frame", "points", g["corners"],
                              meta={k: g[k] for k in ("pixel_space", "spacing_ratio", "strength", "rows", "cols")}))
    return [Cue(state.sheet.digest, "grid", f"{lon},{lat}", (x - 1, y - 1, x + 1, y + 1), "graticule_lines")
            for x, y, lon, lat in g["nodes"]]


# -- the second family: another edition of the same sheet -------------------------------------------------------------
def _fit_of(h):
    """(coeffs, model) of a control-point hypothesis, from its note."""
    model = "poly2" if h.note.startswith("poly2") else "similarity" if h.note.startswith("similarity") else "affine"
    return np.array(ast.literal_eval(h.note.split("coeffs=")[1])), model


def warp_to_grid(gray: np.ndarray, coeffs: np.ndarray, model: str, bounds, res_m: float = 20.0):
    """The scan resampled onto a lon/lat grid over `bounds` through its own placement (sheet px -> lon/lat).
    Returns (image, covered): covered marks grid cells that fall inside the scan."""
    import cv2
    from .generic import apply_transform, fit_transform
    west, south, east, north = bounds
    lat0 = (north + south) / 2
    dlon, dlat = res_m / (111320.0 * math.cos(math.radians(lat0))), res_m / 110574.0
    lons = np.arange(west, east, dlon); lats = np.arange(north, south, -dlat)
    H, W = gray.shape
    gx, gy = np.meshgrid(np.linspace(0, W, 24), np.linspace(0, H, 24))
    px = np.c_[gx.ravel(), gy.ravel()]
    inv, _ = fit_transform(apply_transform(coeffs, px, model), px, "poly2")      # lon/lat -> sheet px
    LL = np.stack(np.meshgrid(lons, lats), -1).reshape(-1, 2)
    m = apply_transform(inv, LL, "poly2").astype(np.float32)
    mx, my = m[:, 0].reshape(len(lats), len(lons)), m[:, 1].reshape(len(lats), len(lons))
    k = max(1, int(round(res_m / max(1e-9, _metres_per_px(coeffs, model, W, H)) / 2)))
    src = cv2.GaussianBlur(255 - gray, (0, 0), k) if k > 1 else 255 - gray
    img = cv2.remap(src.astype(np.float32), mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    covered = (mx >= 0) & (my >= 0) & (mx < W) & (my < H)
    return img, covered, (lons, lats)


def _metres_per_px(coeffs, model, W, H) -> float:
    from .generic import apply_transform
    p = apply_transform(coeffs, np.array([[W / 2, H / 2], [W / 2 + 100, H / 2]], float), model)
    lat = math.radians(p[0, 1])
    return math.hypot((p[1, 0] - p[0, 0]) * 111320.0 * math.cos(lat), (p[1, 1] - p[0, 1]) * 110574.0) / 100


def content_shift(gray_a, fit_a, gray_b, fit_b, bounds, interval_min: float, res_m: float = 20.0):
    """Both scans on one lon/lat grid, each through its own placement; the shift (m) that best aligns their map
    content, by phase correlation. The printed graticule is masked out first: both placements put it on the same
    lon/lat by construction, so it would agree whether the reading was right or not.
    Returns (dx_m, dy_m, response, overlap)."""
    import cv2
    a, ca, (lons, lats) = warp_to_grid(gray_a, *fit_a, bounds, res_m)
    b, cb, _ = warp_to_grid(gray_b, *fit_b, bounds, res_m)
    both = ca & cb
    overlap = float(both.mean())
    if overlap < 0.5:
        return None, None, 0.0, overlap
    keep = both.copy()
    step = interval_min / 60.0
    band = 4
    west, south, east, north = bounds
    for i in range(round((east - west) / step) + 1):
        c = int(round((west + i * step - lons[0]) / (lons[1] - lons[0])))
        keep[:, max(0, c - band):c + band + 1] = False
    for j in range(round((north - south) / step) + 1):
        r = int(round((north - j * step - lats[0]) / (lats[1] - lats[0])))
        keep[max(0, r - band):r + band + 1, :] = False
    def prep(x):
        x = x - cv2.GaussianBlur(x, (0, 0), 12)              # line work, not tint or paper tone
        x[~keep] = 0
        return x.astype(np.float32)
    win = cv2.createHanningWindow((a.shape[1], a.shape[0]), cv2.CV_32F)
    (dx, dy), resp = cv2.phaseCorrelate(prep(a), prep(b), win)
    return dx * res_m, -dy * res_m, float(resp), overlap


def edition_agreement(state, tol_m: float = 60.0, min_response: float = 0.05):
    """Primitive: the sibling scan named in the sheet's meta (`sibling`: id, image, the note of its own
    control-point placement) and this sheet's best placement must put the same map content in the same place.
    Evidence editions_agree True / False with the shift in metres; None when the other scan does not cover this
    sheet or their content does not correlate (a different sheet, a wholly re-surveyed edition)."""
    from ..model import Hypothesis
    sib = state.sheet.meta.get("sibling")
    rec = {**dict(state.sheet.meta), **dict(state.sheet.record)}
    if not sib or not state.hypotheses or not rec.get("bounds"):
        return []
    try:
        fa = _fit_of(state.hypotheses[0])
        fb = _fit_of(Hypothesis("", (0,) * 6, "", "", 0, "", (), sib["note"]))
    except (KeyError, ValueError, SyntaxError, IndexError):
        return [Evidence("editions_agree", None, "deterministic", "edition", note="a placement without fit coefficients")]
    dx, dy, resp, overlap = content_shift(gray_of(state.sheet.image), fa, gray_of(sib["image"]), fb,
                                          [float(v) for v in rec["bounds"]], float(rec.get("interval_min", 5.0)))
    if dx is None:
        return [Evidence("editions_agree", None, "deterministic", "edition",
                         note=f"vs {sib.get('id')}: the other scan covers {overlap:.0%} of this sheet; nothing to compare")]
    if resp < min_response:
        return [Evidence("editions_agree", None, "deterministic", "edition",
                         note=f"vs {sib.get('id')}: content does not correlate (response {resp:.3f}); nothing to compare")]
    d = math.hypot(dx, dy)
    return [Evidence("editions_agree", bool(d <= tol_m), "deterministic", "edition",
                     note=f"vs {sib.get('id')}: content shift {d:.0f} m (dx {dx:+.0f}, dy {dy:+.0f}), response {resp:.3f}; tol {tol_m} m"),
            Evidence("editions_distance_m", round(d, 1), "deterministic", "edition")]


# -- the frame and its marks: graticules printed as lines, as ticks and crosses, or both ----------------------------
def _mark_maps(gray: np.ndarray):
    """Cumulative maps for fast stroke tests: horizontal strokes summed along x, vertical strokes along y (each
    ridge mask thickened by one pixel across the stroke), and paper-vs-ink summed in 2-D."""
    import cv2
    h = cv2.dilate(ridge_mask(gray, "h"), np.ones((3, 1), np.uint8))
    v = cv2.dilate(ridge_mask(gray, "v"), np.ones((1, 3), np.uint8))
    hc = np.zeros((h.shape[0], h.shape[1] + 1), np.float32); hc[:, 1:] = np.cumsum(h, 1)
    vc = np.zeros((v.shape[0] + 1, v.shape[1]), np.float32); vc[1:, :] = np.cumsum(v, 0)
    ink = cv2.integral((gray < 200).astype(np.uint8)).astype(np.float64)
    return hc, vc, ink


def _box(ink, x0, y0, x1, y1) -> float:
    H, W = ink.shape[0] - 1, ink.shape[1] - 1
    x0, x1 = int(max(0, min(W, x0))), int(max(0, min(W, x1))); y0, y1 = int(max(0, min(H, y0))), int(max(0, min(H, y1)))
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return float(ink[y1, x1] - ink[y0, x1] - ink[y1, x0] + ink[y0, x0]) / ((x1 - x0) * (y1 - y0))


def _hrun(hc, y, x0, x1) -> float:
    """Share of [x0, x1) on row y covered by a horizontal stroke."""
    H, W = hc.shape[0], hc.shape[1] - 1
    y = int(round(y)); x0, x1 = int(max(0, min(W, round(x0)))), int(max(0, min(W, round(x1))))
    if not 0 <= y < H or x1 <= x0:
        return 0.0
    return float(hc[y, x1] - hc[y, x0]) / (x1 - x0)


def _vrun(vc, x, y0, y1) -> float:
    H, W = vc.shape[0] - 1, vc.shape[1]
    x = int(round(x)); y0, y1 = int(max(0, min(H, round(y0)))), int(max(0, min(H, round(y1))))
    if not 0 <= x < W or y1 <= y0:
        return 0.0
    return float(vc[y1, x] - vc[y0, x]) / (y1 - y0)


def _cross(hc, vc, x, y, arm: int, gap: int = 3) -> float:
    """A cross (or two crossing lines) centred at (x, y): the weaker of its two strokes, each tested on both sides."""
    h = 0.5 * (_hrun(hc, y, x - arm, x - gap) + _hrun(hc, y, x + gap, x + arm))
    v = 0.5 * (_vrun(vc, x, y - arm, y - gap) + _vrun(vc, x, y + gap, y + arm))
    return min(h, v)


def _tick(hc, vc, x, y, side: str, arm: int, gap: int = 3) -> tuple[float, float]:
    """A tick at a neatline point: a stroke perpendicular to the edge on one side of it. Returns (one-sidedness,
    stronger side). A ruled grid crosses the neatline and runs on both sides; a graticule tick or meridian does not."""
    if side in ("top", "bottom"):
        a, b = _vrun(vc, x, y - gap - arm, y - gap), _vrun(vc, x, y + gap, y + gap + arm)
    else:
        a, b = _hrun(hc, y, x - gap - arm, x - gap), _hrun(hc, y, x + gap, x + gap + arm)
    return max(a, b) - min(a, b), max(a, b)


def _search(fn, x, y, r: int, step: int = 1):
    best = (-1.0, x, y)
    for dy in range(-r, r + 1, step):
        for dx in range(-r, r + 1, step):
            v = fn(x + dx, y + dy)
            if v > best[0]:
                best = (v, x + dx, y + dy)
    return best


def _corner(hl, vl):
    """Intersection of a horizontal line y = a x + b with a vertical line x = c y + d."""
    a, b = hl; c, d = vl
    y = (a * d + b) / (1 - a * c)
    return c * y + d, y


def read_frame_marks(gray: np.ndarray, west: float, south: float, east: float, north: float, interval_min: float = 5.0,
                     pixel_space: str = "paper", ratio_tol: float = 0.03, top_k: int = 6, mark_min: float = 0.5,
                     band: float = 0.012, max_frames: int = 12, same_place_m: float = 60.0):
    """The neatline and the graticule marks on it and inside it, for sheets that print the graticule as full lines,
    as edge ticks and interior crosses, or as both.

    1. Neatline: among rectangles of long lines with the shape of the record's bounds (cos(lat) x the bounds on paper;
       the bounds as they are only for a raster the record says is in degrees), the one where the map content stops
       on every side (judged by its weakest side) and whose edge nodes carry one-sided marks. A ruled grid (sections,
       roads) runs on both sides of its lines and does not stop the content. A rival frame scoring nearly as well makes
       the reading ambiguous only if it would place the sheet elsewhere (a corner moved by more than `same_place_m`,
       the edition tolerance); a near-duplicate line (double neatline) is the same placement. ("The outermost frame with marks" was tried on the development set and fails:
       a collar line just outside the neatline picks up the corner labels as marks.)
    2. Every graticule node of the bounds is predicted from the four corners and confirmed or not: a one-sided tick
       on the edges, a cross inside. Confirmed nodes and the four corners are returned with their printed lon/lat.
    Returns a dict with found False and the reason when no rectangle fits."""
    step = interval_min / 60.0
    n_cols, n_rows = round((east - west) / step), round((north - south) / step)
    if n_cols < 1 or n_rows < 1:
        raise ValueError("bounds smaller than one graticule interval")
    lat0 = (north + south) / 2
    # a scan of a paper sheet has metric pixels; "degrees" is for a raster already resampled to lon/lat, and only
    # the record can say so. Trying both lets a ruled square grid pass for a graticule.
    shapes = {"paper": math.cos(math.radians(lat0)) * (east - west) / (north - south), "degrees": (east - west) / (north - south)}
    expected = {k: v for k, v in shapes.items() if pixel_space in (k, "auto")}
    H, W = gray.shape
    hl, hs, hctx = find_lines(gray, "h")
    vl, vs, vctx = find_lines(gray, "v")
    hc, vc, ink = _mark_maps(gray)
    if len(hl) < 2 or len(vl) < 2:
        return {"found": False, "why": f"{len(hl)} horizontal and {len(vl)} vertical long lines"}
    B = max(6, int(band * max(H, W)))
    # each long line refined once; candidate edges are scored by where the content stops
    H_ = {ln[0]: refine_line(*hctx, ln[0], ln[2])[:2] for ln in hl}
    V_ = {ln[0]: refine_line(*vctx, ln[0], ln[2])[:2] for ln in vl}
    def edge_scores(pos, axis):
        if axis == "h":
            a = _box(ink, 0.2 * W, pos - B, 0.8 * W, pos - 3); b = _box(ink, 0.2 * W, pos + 3, 0.8 * W, pos + B)
        else:
            a = _box(ink, pos - B, 0.2 * H, pos - 3, 0.8 * H); b = _box(ink, pos + 3, 0.2 * H, pos + B, 0.8 * H)
        return b - a, a - b                                   # (as a top / left edge, as a bottom / right edge)
    hp = [ln[0] for ln in hl]; vp = [ln[0] for ln in vl]
    hs_ = {p: edge_scores(p, "h") for p in hp}; vs_ = {p: edge_scores(p, "v") for p in vp}
    tops = sorted(hp, key=lambda p: -hs_[p][0])[:top_k]
    bots = sorted(hp, key=lambda p: -hs_[p][1])[:top_k]
    lefts = sorted(vp, key=lambda p: -vs_[p][0])[:top_k]
    rights = sorted(vp, key=lambda p: -vs_[p][1])[:top_k]
    rects = []
    for t in tops:
        for b in bots:
            if b - t < 0.25 * H:
                continue
            for l in lefts:
                for r in rights:
                    if r - l < 0.25 * W:
                        continue
                    ratio = (r - l) / (b - t)
                    for space, e in expected.items():
                        if abs(ratio / e - 1) <= ratio_tol:
                            # a neatline stops the content on every side: the frame is as good as its weakest side
                            contrast = min(hs_[t][0], hs_[b][1], vs_[l][0], vs_[r][1])
                            rects.append((contrast, t, b, l, r, space, ratio))
    if not rects:
        return {"found": False, "why": f"{len(hl)} x {len(vl)} long lines; no rectangle with the shape of the bounds"}
    rects.sort(key=lambda x: -x[0])

    def evaluate(rect):
        contrast, t, b, l, r, space, ratio = rect
        tl, tr = _corner(H_[t], V_[l]), _corner(H_[t], V_[r])
        bl, br = _corner(H_[b], V_[l]), _corner(H_[b], V_[r])
        dx, dy = (r - l) / n_cols, (b - t) / n_rows
        arm = max(8, int(0.01 * min(dx, dy))); rad = max(4, int(0.012 * min(dx, dy)))
        def at(i, j):                                          # bilinear from the corners: curvature over 15' is ~1 px
            u, v = i / n_cols, j / n_rows
            top = (tl[0] + u * (tr[0] - tl[0]), tl[1] + u * (tr[1] - tl[1]))
            bot = (bl[0] + u * (br[0] - bl[0]), bl[1] + u * (br[1] - bl[1]))
            return top[0] + v * (bot[0] - top[0]), top[1] + v * (bot[1] - top[1])
        nodes, edge_s, inner_s = [(tl[0], tl[1], west, north), (tr[0], tr[1], east, north), (bl[0], bl[1], west, south), (br[0], br[1], east, south)], [], []
        for j in range(n_rows + 1):
            for i in range(n_cols + 1):
                if (i in (0, n_cols)) and (j in (0, n_rows)):
                    continue
                x, y = at(i, j)
                lon, lat = west + i * step, north - j * step
                if i in (0, n_cols) or j in (0, n_rows):
                    side = "top" if j == 0 else "bottom" if j == n_rows else "left" if i == 0 else "right"
                    along = (lambda q, _x=x, _y=y, _s=side: (_x + q, _y) if _s in ("top", "bottom") else (_x, _y + q))
                    (one, strong), q = max(((_tick(hc, vc, *along(q), side, arm), q) for q in range(-rad, rad + 1)), key=lambda z: z[0][0])
                    ok = one >= mark_min and strong >= mark_min
                    edge_s.append(ok)
                    if ok:
                        nodes.append((*along(q), lon, lat))
                else:
                    v, cx, cy = _search(lambda X, Y: _cross(hc, vc, X, Y, arm), int(round(x)), int(round(y)), rad)
                    inner_s.append(v >= mark_min)
                    if v >= mark_min:
                        nodes.append((float(cx), float(cy), lon, lat))
        e_frac = float(np.mean(edge_s)) if edge_s else 0.0
        i_frac = float(np.mean(inner_s)) if inner_s else 1.0
        marks = (len(nodes) - 4) / max(1, len(edge_s) + len(inner_s))
        return {"score": contrast + e_frac + 0.5 * i_frac, "contrast": contrast, "edge_marks": e_frac, "inner_marks": i_frac, "marks": marks,
                "nodes": nodes, "pixel_space": space, "ratio": ratio, "expected_ratio": expected[space],
                "corners": [tl, tr, br, bl], "lines": (t, b, l, r)}

    scored = sorted((evaluate(r) for r in rects[:max_frames]), key=lambda z: -z["score"])
    best = scored[0]
    # a rival is another reading only if it puts the sheet somewhere else: a frame whose corners lie within
    # `same_place_m` of the best one's (a double neatline, a road along the edge) is the same placement, not a doubt
    t, b, l, r = best["lines"]
    mpp = (north - south) * 110574.0 / max(1.0, b - t)                    # ground metres per pixel, from the frame
    def moved_m(z):
        return max(math.hypot(p[0] - q[0], p[1] - q[1]) for p, q in zip(z["corners"], best["corners"])) * mpp
    rival = next((z for z in scored[1:] if moved_m(z) > same_place_m), None)
    return {"found": True, **best, "rival_score": rival["score"] if rival else None,
            "rival_moved_m": round(moved_m(rival), 1) if rival else None, "metres_per_px": mpp,
            "rival": {k: rival[k] for k in ("score", "contrast", "edge_marks", "inner_marks", "marks", "lines")} if rival else None,
            "n_expected_marks": (n_cols + 1) * (n_rows + 1) - 4}


def ruled_out(best: dict, rival: dict, contrast_margin: float = 0.05) -> bool:
    """Does the evidence rule the rival frame out? Marks saturate (a sub-grid of section lines can carry every mark),
    so they cannot separate two frames that both have them; where the map content stops can. The rival is ruled out
    when the content stops clearly better at the chosen frame and its marks are at least as complete."""
    return best["contrast"] - rival["contrast"] >= contrast_margin and best["marks"] >= rival["marks"]


def graticule_marks(state, interval_min: float = 5.0, ambiguity: float = 0.85, min_marks: float = 0.5):
    """Primitive: the record's neatline bounds and interval -> the four neatline corners and every graticule node
    confirmed by a mark (one-sided edge tick, interior cross, or crossing graticule lines), as grid cues; evidence on
    the frame (where content stops), the share of marks found, and how clear the choice of frame was. A frame whose
    marks are mostly missing yields nothing: four corners alone do not show that the rectangle is the neatline."""
    rec = {**dict(state.sheet.meta), **dict(state.sheet.record)}
    b = rec.get("bounds")
    if not b:
        return []
    west, south, east, north = (float(v) for v in b)
    interval_min = float(rec.get("interval_min", interval_min))
    g = read_frame_marks(gray_of(state.sheet.image), west, south, east, north, interval_min, rec.get("pixel_space", "paper"))
    if not g["found"]:
        state.evidence.append(Evidence("graticule_found", False, "deterministic", "sheet-reader", note=g["why"][:200]))
        return []
    marks = (len(g["nodes"]) - 4) / max(1, g["n_expected_marks"])
    # ambiguous: a frame that would place the sheet elsewhere (read_frame_marks keeps only those), scoring nearly as
    # well, and not ruled out by the evidence that separates frames
    rival = g["rival_score"]
    close = rival is not None and rival >= ambiguity * g["score"]
    excluded = close and ruled_out(g, g["rival"])
    ambiguous = close and not excluded
    found = marks >= min_marks
    state.evidence.append(Evidence("graticule_found", bool(found), "deterministic", "sheet-reader",
                                   note=f"{len(g['nodes'])} nodes (4 corners + {len(g['nodes']) - 4}/{g['n_expected_marks']} marks: edge {g['edge_marks']:.0%}, "
                                        f"inside {g['inner_marks']:.0%}); content stops at the frame by {g['contrast']:.2f}; "
                                        f"shape {g['ratio']:.4f} (expected {g['expected_ratio']:.4f}, {g['pixel_space']})"))
    state.evidence.append(Evidence("graticule_marks", round(marks, 3), "deterministic", "sheet-reader"))
    state.evidence.append(Evidence("graticule_ambiguous", bool(ambiguous), "deterministic", "sheet-reader",
                                   note=(f"best frame {g['score']:.2f}; the strongest frame placing the sheet elsewhere {rival:.2f} "
                                         f"(corners moved up to {g['rival_moved_m']:.0f} m; content stops {g['contrast']:.2f} vs {g['rival']['contrast']:.2f}, "
                                         f"marks {g['marks']:.2f} vs {g['rival']['marks']:.2f}"
                                         + ("; ruled out" if excluded else "") + ")") if rival is not None else "no frame placing the sheet elsewhere"))
    if not found:
        return []
    state.layers.append(Layer(state.sheet.digest, "frame", "points", g["corners"],
                              meta={k: g[k] for k in ("pixel_space", "ratio", "contrast", "edge_marks", "inner_marks")}))
    return [Cue(state.sheet.digest, "grid", f"{lon},{lat}", (x - 1, y - 1, x + 1, y + 1), "graticule_marks")
            for x, y, lon, lat in g["nodes"]]


register(Primitive("graticule_lines", "sheet-reader", True, (), "cue",
                   "generic graticule reader: the record's neatline bounds + interval -> every meridian x parallel node as a grid cue; "
                   "thin-line profiles, evenly spaced families, spacing ratio checked against cos(latitude); OpenCV only",
                   graticule_lines, "generic", requires=("opencv",), sheet_params=("interval_min",)))
register(Primitive("edition_agreement", "geometry", True, ("hypothesis",), "evidence",
                   "another edition of the same sheet, placed on its own: both scans warped onto one lon/lat grid through their own "
                   "placements, graticule masked, map content phase-correlated; the shift must be near zero", edition_agreement, "generic", requires=("opencv",)))
register(Primitive("graticule_marks", "sheet-reader", True, (), "cue",
                   "generic graticule reader for lines, ticks and crosses: the neatline (shape of the bounds, content stops at it, "
                   "one-sided edge marks) and every node confirmed by a mark -> grid cues; OpenCV only",
                   graticule_marks, "generic", requires=("opencv",), sheet_params=("interval_min",)))
