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
    """Long straight lines along one axis. Returns (lines, slope): each line is (position at mid-span, strength),
    strength being the share of the span on which the line is present. A global skew is searched first; each line's
    own slope (meridians converge) is refined later, on the lines that are kept."""
    mask = ridge_mask(gray, axis)
    P, centres, L, W = _strip_profiles(mask, axis, n_strips)
    best = None
    for s in np.linspace(-max_slope, max_slope, 201):
        prof = _shifted_sum(P, centres, W, s)
        sc = float(np.sort(prof)[-16:].sum())
        if best is None or sc > best[0]:
            best = (sc, float(s), prof)
    _, slope, prof = best
    prof = prof.copy()
    sep = max(8, int(0.01 * L))
    out = []
    while True:
        i = int(prof.argmax()); v = float(prof[i])
        if v < min_strength:
            break
        out.append((float(i), v))
        prof[max(0, i - sep):i + sep + 1] = 0
    return sorted(out), slope, (P, centres, W)


def families(lines, n: int, length: int, min_interval: float = 0.08, tol: float = 0.012):
    """Every set of n+1 evenly spaced lines among `lines`: (mean strength, positions, spacing), best first. The two
    ends fix the spacing; each interior line must be found within `tol` of an interval of its expected place."""
    pos = np.array([p for p, _ in lines]); st = np.array([s for _, s in lines])
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
    hlines = [refine_line(*hctx, p, hs) for p in fh[1]]          # y = a x + b
    vlines = [refine_line(*vctx, p, vs) for p in fv[1]]          # x = c y + d
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


register(Primitive("graticule_lines", "sheet-reader", True, (), "cue",
                   "generic graticule reader: the record's neatline bounds + interval -> every meridian x parallel node as a grid cue; "
                   "thin-line profiles, evenly spaced families, spacing ratio checked against cos(latitude); OpenCV only",
                   graticule_lines, "generic", requires=("opencv",), sheet_params=("interval_min",)))
register(Primitive("edition_agreement", "geometry", True, ("hypothesis",), "evidence",
                   "another edition of the same sheet, placed on its own: both scans warped onto one lon/lat grid through their own "
                   "placements, graticule masked, map content phase-correlated; the shift must be near zero", edition_agreement, "generic", requires=("opencv",)))
