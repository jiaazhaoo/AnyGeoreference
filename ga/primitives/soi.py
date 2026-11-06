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
    data = osm.fetch((s, w, n, e), state.sheet.meta.get("cache_dir", "/tmp/ga-osm"))
    return [Layer(state.sheet.digest, "reference_vectors", "vectors", data, frame="EPSG:4326", meta={"bbox": (s, w, n, e)})]


for p in (
    Primitive("graticule_frame", "sheet-reader", True, (), "cue", "neatline + graticule nodes with their printed lon/lat", graticule_frame, "soi", requires=("autogeoref", "opencv")),
    Primitive("plate_separation", "sheet-reader", True, (), "layer", "colour-plate masks: black / red / blue inks", plate_separation, "soi", requires=("autogeoref", "opencv")),
    Primitive("line_structure", "sheet-reader", True, ("layer",), "layer", "skeletonised, traced linework of a plate as polylines", line_structure, "soi", requires=("autogeoref", "scikit-image")),
    Primitive("osm_reference", "basemap", True, ("candidate",), "layer", "OSM skeleton (rail, canals, rivers, roads, villages) for the candidate area", osm_reference, "soi", requires=("autogeoref", "Overpass")),
    Primitive("structure_match", "basemap", True, ("layer",), "hypothesis", "MINIMA-LoFTR match of the sheet's linework against the rendered reference -> GCPs -> robust polynomial", None, "soi", requires=("autogeoref", "MINIMA weights", "torch")),
    Primitive("cross_edition_agreement", "geometry", True, ("hypothesis",), "evidence", "the same sheet in two editions placed independently: do the placements agree", None, "soi"),
):
    register(p)
