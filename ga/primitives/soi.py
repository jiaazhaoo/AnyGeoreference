"""Primitives bound to the historical-map project (autogeoref: Survey of India sheets). Lazy imports."""
from __future__ import annotations

import os
import sys

import numpy as np

from ..model import Cue, Hypothesis, Layer
from . import Primitive, register
from evalcore import Evidence

SOI = os.environ.get("SOI_REPO", "/env/code/autogeoref-soi")


def _soi():
    if SOI not in sys.path:
        sys.path.insert(0, SOI)
    from autogeoref import frame, sheets, plates, osm, features    # noqa: E402
    return frame, sheets, plates, osm, features


def _img(state):
    """BGR pixels of the sheet. A GeoTIFF is read with rasterio (its georeference is NOT used: the loop must earn
    the placement itself); anything else with OpenCV."""
    import cv2
    path = state.sheet.image
    if path.lower().endswith((".tif", ".tiff")):
        import rasterio
        with rasterio.open(path) as ds:
            arr = ds.read([1, 2, 3]) if ds.count >= 3 else np.repeat(ds.read([1]), 3, axis=0)
        return np.ascontiguousarray(arr.transpose(1, 2, 0)[..., ::-1])
    img = cv2.imread(path)
    if img is None:
        raise FileNotFoundError(path)
    return img


def graticule_frame(state):
    """Neatline + 5' graticule nodes -> grid cues 'lon,lat' at their pixel (sheet code from the record)."""
    frame, sheets, *_ = _soi()
    from autogeoref import georef as soi_georef
    import math
    code = state.sheet.record.get("sheet_code") or state.sheet.meta.get("sheet_code")
    if not code:
        return []
    sh = sheets.parse(code)
    dlon, dlat = sh.size_deg
    lat0 = (sh.north + sh.south) / 2
    step = soi_georef.GRID_MIN
    img = _img(state)
    n_cols, n_rows = round(dlon * 60 / step), round(dlat * 60 / step)
    # the neatline's pixel aspect depends on what the pixels are: paper (metric, cos(lat) squeezes longitude) or a
    # raster already resampled to degrees (1 : 1). "auto" tries paper first, then degrees, and records which held.
    ratios = {"paper": math.cos(math.radians(lat0)) * dlon / dlat, "degrees": dlon / dlat}
    want = state.sheet.meta.get("pixel_space", "auto")
    tried, fr, used = [], None, None
    for name in ([want] if want in ratios else ["paper", "degrees"]):
        try:
            fr = frame.detect(img, n_cols, n_rows, ratios[name]); used = name
            break
        except RuntimeError as e:                               # noqa: PERF203
            tried.append(f"{name}: {e}")
    if fr is None:
        return []
    px, ll = soi_georef.gcps(fr, sh)
    out = [Cue(state.sheet.digest, "grid", f"{lon},{lat}", (float(x) - 1, float(y) - 1, float(x) + 1, float(y) + 1), "graticule_frame")
           for (x, y), (lon, lat) in zip(px, ll)]
    state.layers.append(Layer(state.sheet.digest, "frame", "points", fr.corners, meta={"skew_deg": fr.skew_deg, "fit_rms_px": fr.fit_rms_px,
                                                                                    "n_nodes": len(px), "pixel_space": used, "tried": tried}))
    return out


def plate_separation(state):
    _, _, plates, *_ = _soi()
    p = plates.separate(_img(state))
    return [Layer(state.sheet.digest, name, "mask", getattr(p, name)) for name in ("black", "red", "blue") if hasattr(p, name)]


def line_structure(state, plate: str = "black"):
    """Skeletonised, traced linework of one plate -> polylines in sheet pixels (features.trace)."""
    *_, features = _soi()
    lay = state.layer(plate)
    if lay is None:
        return []
    from skimage.morphology import skeletonize
    skel = skeletonize(lay.data > 0)
    lines = features.link(features.trace(skel))
    return [Layer(state.sheet.digest, "line_structure", "polylines", lines, meta={"plate": plate})]


def osm_reference(state, layers=None):
    """Fetch OSM skeleton layers for the candidate area and render them on a metric grid -> raster layer."""
    *_, osm, _ = _soi()
    if not state.candidates:
        return []
    import shapely.wkt
    g = shapely.wkt.loads(state.candidates[0].area_wkt)
    w, s, e, n = g.bounds
    import requests, time as _t
    mirrors = [m for m in os.environ.get("OSM_OVERPASS_URLS", "https://overpass-api.de/api/interpreter,https://lz4.overpass-api.de/api/interpreter,"
                                         "https://z.overpass-api.de/api/interpreter,https://overpass.kumi.systems/api/interpreter").split(",") if m]
    data, last = None, None
    for attempt in range(2):
        for m in mirrors:
            osm.OVERPASS = m
            try:
                data = osm.fetch((w, s, e, n), state.sheet.meta.get("cache_dir", "/tmp/ga-osm"))
                break
            except (requests.HTTPError, requests.ConnectionError, requests.Timeout, ValueError) as err:   # noqa: PERF203
                last = f"{m}: {err}"[:120]; _t.sleep(3)
        if data is not None:
            break
    if data is None:
        state.evidence.append(Evidence("osm_fetch_failed", True, "deterministic", "basemap", note=last or "no mirror answered"))
        return []
    return [Layer(state.sheet.digest, "reference_vectors", "vectors", data, frame="EPSG:4326", meta={"bbox": (s, w, n, e)})]


def structure_match(state, res_m: float = 10.0, max_windows: int | None = None, device: str | None = None):
    """MINIMA-LoFTR registration of the sheet's linework against rendered OSM, window by window (the project's
    refine.py): accepted windows give GCPs raw px <-> OSM lon/lat; a robust 2nd-order polynomial over all of them is
    the hypothesis. Needs the sheet code (for the step-1 frame) and the OSM vectors layer from `osm_reference`."""
    frame, sheets, plates, osm, features = _soi()
    from autogeoref import georef as soi_georef, refine
    import torch
    code = state.sheet.record.get("sheet_code") or state.sheet.meta.get("sheet_code")
    ref = state.layer("reference_vectors")
    if not code or ref is None:
        return []
    img = _img(state)
    grid_cues = [c for c in state.cues if c.kind == "grid" and "," in c.text]
    if grid_cues:                                               # the frame was already read: build step 1 from those nodes
        sh = sheets.parse(code)
        px = np.array([[(c.bbox[0] + c.bbox[2]) / 2, (c.bbox[1] + c.bbox[3]) / 2] for c in grid_cues])
        ll = np.array([[float(v) for v in c.text.split(",")[:2]] for c in grid_cues])
        fwd, inv = soi_georef.Poly.fit(px, ll, 2), soi_georef.Poly.fit(ll, px, 2)
        lat0 = (sh.north + sh.south) / 2
        mx, my = soi_georef.metres_per_deg(lat0)
        d = fwd(px) - ll
        s1 = soi_georef.Step1(sh, None, px, ll, fwd, inv, np.hypot(d[:, 0] * mx, d[:, 1] * my))
    else:
        s1 = soi_georef.run(img, code, order=2)
    grid = refine.make_grid(s1, res_m)
    wins = refine.windows(grid, s1.sheet)
    if max_windows:
        wins = wins[:max_windows]
    dev = device or ("cuda" if torch.cuda.is_available() and not state.sheet.meta.get("cpu_only") else "cpu")
    matcher = refine.load_matcher()
    raw, true, group, results = [], [], [], []
    for gi, (x0, y0) in enumerate(wins):
        win = refine.scan_window(img, s1, grid, x0, y0, refine.WIN, refine.WIN)
        scan_bin = refine.binarise(win, grid, x0, y0, s1.sheet)
        osm_bin = refine.osm_window(ref.data, grid, x0, y0, refine.WIN, refine.WIN)
        r = refine.match_window(matcher, scan_bin, osm_bin, s1, grid, x0, y0)
        results.append(r)
        if r.accepted:
            raw.append(r.raw_px); true.append(r.true_ll); group.append(np.full(len(r.raw_px), gi))
    n_acc = sum(1 for r in results if r.accepted)
    if not raw or sum(len(a) for a in raw) < 12:
        state.evidence.append(Evidence("structure_windows_accepted", n_acc, "deterministic", "basemap", note=f"of {len(results)}"))
        return []
    raw_px, true_ll, grp = np.vstack(raw), np.vstack(true), np.concatenate(group)
    lat0 = (s1.sheet.north + s1.sheet.south) / 2
    P, keep, res = refine.fit_robust(raw_px, true_ll, grp, order=2, lat0=lat0)
    loo = refine.loo_windows(raw_px, true_ll, grp, keep, order=2, lat0=lat0)
    # the project's Poly works on normalised inputs: the affine summary is taken from its values at three points
    o, ex, ey = P(np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]]))
    T6 = (float(ex[0] - o[0]), float(ey[0] - o[0]), float(o[0]), float(ex[1] - o[1]), float(ey[1] - o[1]), float(o[1]))
    coeffs = np.asarray(P.coef)
    H, W = img.shape[:2]
    corners = P(np.array([[0, 0], [W, 0], [W, H], [0, H]], float))
    wkt = "POLYGON((" + ",".join(f"{x} {y}" for x, y in corners) + f",{corners[0][0]} {corners[0][1]}))"
    rms = float(np.sqrt(np.mean(res[keep] ** 2)))
    loo_med = float(np.nanmedian(loo)) if np.isfinite(loo).any() else None
    state.evidence.append(Evidence("structure_windows_accepted", n_acc, "deterministic", "basemap", note=f"of {len(results)}; GCPs {int(keep.sum())}/{len(keep)}"))
    state.evidence.append(Evidence("structure_loo_median_m", loo_med, "deterministic", "basemap", note="leave-one-window-out residual"))
    score = min(1.0, n_acc / max(1, len(results))) * (1.0 / (1.0 + rms / 30))
    return [Hypothesis(state.sheet.digest, T6, wkt, "EPSG:4326", float(score), "structure_match", (),
                       note=f"poly2-normalised; n={int(keep.sum())}; rms={rms:.4g}; windows {n_acc}/{len(results)}; loo_median_m={loo_med}; mu={P.mu.tolist()}; sd={P.sd.tolist()}; coeffs={coeffs.tolist()}")]


for p in (
    Primitive("graticule_frame", "sheet-reader", True, (), "cue", "neatline + graticule nodes with their printed lon/lat", graticule_frame, "soi", requires=("autogeoref", "opencv")),
    Primitive("plate_separation", "sheet-reader", True, (), "layer", "colour-plate masks: black / red / blue inks", plate_separation, "soi", requires=("autogeoref", "opencv")),
    Primitive("line_structure", "sheet-reader", True, ("layer",), "layer", "skeletonised, traced linework of a plate as polylines", line_structure, "soi", requires=("autogeoref", "scikit-image")),
    Primitive("osm_reference", "basemap", True, ("candidate",), "layer", "OSM skeleton (rail, canals, rivers, roads, villages) for the candidate area", osm_reference, "soi", requires=("autogeoref", "Overpass")),
    Primitive("structure_match", "basemap", True, ("layer",), "hypothesis", "MINIMA-LoFTR match of the sheet's linework against rendered OSM, window by window -> GCPs -> robust polynomial", structure_match, "soi", requires=("autogeoref", "MINIMA weights", "torch", "Overpass")),
    Primitive("cross_edition_agreement", "geometry", True, ("hypothesis",), "evidence", "the same sheet in two editions placed independently: do the placements agree", None, "soi"),
):
    register(p)
