"""Primitives for the third kind: a raster with no usable text (aerial / satellite tile, an unlabelled map extract).
Only structure is available: linework or edges on the image, matched against rendered reference vectors over a
candidate area that must come from somewhere else (the record, a user hint, a coarse geocode). With no candidate
area the loop abstains, by design."""
from __future__ import annotations

import numpy as np

import os

from ..model import Candidate, Hypothesis, Layer
from . import Primitive, register
from evalcore import Evidence


def edge_structure(state, low: int = 60, high: int = 150):
    """Canny edges -> a mask layer; the generic reader for images without colour plates or text."""
    import cv2
    img = cv2.imread(state.sheet.image, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(state.sheet.image)
    return [Layer(state.sheet.digest, "edges", "mask", cv2.Canny(img, low, high))]


def hint_area(state, radius_m: float = 2000.0, crs: str = "EPSG:27700"):
    """A candidate area from the record's own hint (a point or a bbox the user supplied). No hint -> no candidate."""
    h = state.sheet.record.get("hint_xy") or state.sheet.meta.get("hint_xy")
    if not h:
        return []
    x, y = float(h[0]), float(h[1]); r = radius_m
    wkt = f"POLYGON(({x-r} {y-r},{x+r} {y-r},{x+r} {y+r},{x-r} {y+r},{x-r} {y-r}))"
    return [Candidate(state.sheet.digest, "record-text", wkt, crs, ("hint",), 0.5, note="user / record hint")]


def overlay_agreement(state, tol_px: int = 3):
    """Fraction of the sheet's structure pixels that land within tol_px of reference structure after the best
    hypothesis' transform; computed on rasters in the reference frame. Needs 'edges' or 'line_structure' and a
    'reference_render' layer."""
    import cv2
    ref = state.layer("reference_render")
    src = state.layer("edges") or state.layer("line_structure")
    if ref is None or src is None or not state.hypotheses:
        return []
    ref_mask = (ref.data > 0).astype(np.uint8)
    dist = cv2.distanceTransform(1 - ref_mask, cv2.DIST_L2, 3)
    a, b, c, d, e, f = state.hypotheses[0].transform          # sheet px -> CRS
    T = np.array([[a, b, c], [d, e, f], [0, 0, 1]], float)
    x0, y0, x1, y1 = ref.meta["bbox"]; r = ref.meta["res_m"]
    Ginv = np.array([[1 / r, 0, -x0 / r], [0, -1 / r, y1 / r], [0, 0, 1]])   # CRS -> reference px
    M = (Ginv @ T)[:2]                                           # sheet px -> reference px
    if src.kind == "mask":
        warped = cv2.warpAffine((src.data > 0).astype(np.uint8), M, (ref_mask.shape[1], ref_mask.shape[0]))
        ys, xs = np.nonzero(warped)
    else:
        pts = np.concatenate([np.asarray(l, float) for l in src.data]) if src.data else np.zeros((0, 2))
        p = (M[:, :2] @ pts.T).T + M[:, 2]
        xs, ys = p[:, 0].astype(int), p[:, 1].astype(int)
        keep = (xs >= 0) & (ys >= 0) & (xs < ref_mask.shape[1]) & (ys < ref_mask.shape[0])
        xs, ys = xs[keep], ys[keep]
    if len(xs) == 0:
        return [Evidence("overlay_agreement", 0.0, "deterministic", "basemap")]
    frac = float(np.mean(dist[ys, xs] <= tol_px))
    return [Evidence("overlay_agreement", frac, "deterministic", "basemap", note=f"{len(xs)} structure pixels, tol {tol_px}px")]


# -- generic reference rendering and structure matching ------------------------------------------------------------
def _lines_from_gpkg(gpkg: str, layers: tuple, bbox: tuple):
    """Line geometries intersecting bbox (x0, y0, x1, y1) from a GeoPackage with rtree indexes (OS Zoomstack layout)."""
    import sqlite3
    from shapely import wkb
    x0, y0, x1, y1 = bbox
    if not os.path.isabs(gpkg):
        for base in ("/data/reference/base-data/os_opendata", "/data/reference/base-data", "/data/reference/os"):
            if os.path.exists(os.path.join(base, gpkg)):
                gpkg = os.path.join(base, gpkg); break
    if not os.path.exists(gpkg):
        raise FileNotFoundError(f"GeoPackage not found: {gpkg}")
    con = sqlite3.connect(f"file:{gpkg}?mode=ro", uri=True)
    out = []
    for layer in layers:
        q = (f"SELECT t.geom FROM {layer} t JOIN rtree_{layer}_geom r ON t.fid = r.id "
             f"WHERE r.minx <= ? AND r.maxx >= ? AND r.miny <= ? AND r.maxy >= ?")
        try:
            rows = con.execute(q, (x1, x0, y1, y0)).fetchall()
        except sqlite3.OperationalError:
            rows = con.execute(q.replace("t.fid", "t.id"), (x1, x0, y1, y0)).fetchall()
        for (blob,) in rows:
            hdr = 8 + (4 * ((blob[3] & 0x0E) // 2 and {0: 0, 1: 8, 2: 12, 3: 12, 4: 16}[(blob[3] & 0x0E) >> 1]))   # GeoPackage binary header
            try:
                out.append(wkb.loads(bytes(blob[hdr:])))
            except Exception:                                       # noqa: BLE001
                continue
    return out


def render_lines(geoms, bbox: tuple, res_m: float, width_px: int = 2) -> np.ndarray:
    """Rasterise line geometries over bbox at res_m metres per pixel: white lines on black (uint8 mask)."""
    import cv2
    x0, y0, x1, y1 = bbox
    W, H = int(round((x1 - x0) / res_m)), int(round((y1 - y0) / res_m))
    img = np.zeros((H, W), np.uint8)
    def to_px(coords):
        c = np.asarray(coords, float)
        return np.c_[(c[:, 0] - x0) / res_m, (y1 - c[:, 1]) / res_m].round().astype(np.int32)
    for g in geoms:
        parts = getattr(g, "geoms", [g])
        for part in parts:
            if part.geom_type == "LineString":
                cv2.polylines(img, [to_px(part.coords)], False, 255, width_px)
            elif part.geom_type == "Polygon":
                cv2.polylines(img, [to_px(part.exterior.coords)], True, 255, width_px)
    return img


def reference_render(state, gpkg: str | None = None, layers: tuple = ("roads_local", "roads_regional", "roads_national", "rail"),
                     res_m: float = 2.0):
    """Reference structure over the first candidate area: line layers of a GeoPackage rendered on a metric grid."""
    if not state.candidates:
        return []
    import shapely.wkt
    gpkg = gpkg or os.environ.get("GA_REFERENCE_GPKG", "/data/reference/base-data/os_opendata/OS_Open_Zoomstack.gpkg")
    g = shapely.wkt.loads(state.candidates[0].area_wkt)
    bbox = tuple(g.bounds)
    img = render_lines(_lines_from_gpkg(gpkg, layers, bbox), bbox, res_m)
    return [Layer(state.sheet.digest, "reference_render", "mask", img, frame=state.candidates[0].crs,
                  meta={"bbox": bbox, "res_m": res_m, "layers": list(layers)})]


def structure_match(state, min_inliers: int = 12, ransac_px: float = 4.0, nfeatures: int = 4000):
    """Deterministic feature match (ORB + RANSAC similarity) of the sheet's structure mask against the reference
    render -> a hypothesis in the reference CRS. Generic and weak by design: a baseline every kind can run."""
    import cv2
    ref = state.layer("reference_render")
    src = state.layer("edges") or state.layer("line_structure")
    if ref is None or src is None or src.kind != "mask":
        return []
    cv2.setRNGSeed(0)
    orb = cv2.ORB_create(nfeatures=nfeatures)
    a = (src.data > 0).astype(np.uint8) * 255
    b = (ref.data > 0).astype(np.uint8) * 255
    k1, d1 = orb.detectAndCompute(a, None)
    k2, d2 = orb.detectAndCompute(b, None)
    if d1 is None or d2 is None or len(k1) < min_inliers or len(k2) < min_inliers:
        return []
    matches = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(d1, d2)
    if len(matches) < min_inliers:
        return []
    p0 = np.float32([k1[m.queryIdx].pt for m in matches]); p1 = np.float32([k2[m.trainIdx].pt for m in matches])
    M, inl = cv2.estimateAffinePartial2D(p0, p1, method=cv2.RANSAC, ransacReprojThreshold=ransac_px, maxIters=5000, confidence=0.999)
    if M is None or inl is None or int(inl.sum()) < min_inliers:
        return []
    n_in = int(inl.sum())
    # pixel-to-pixel (sheet -> reference raster) composed with the raster's georeference -> sheet -> CRS
    x0, y0, x1, y1 = ref.meta["bbox"]; r = ref.meta["res_m"]
    G = np.array([[r, 0, x0], [0, -r, y1]])                       # reference px -> CRS
    A = np.vstack([M, [0, 0, 1]])
    T = G @ A                                                     # 2x3 sheet px -> CRS
    H, W = a.shape
    corners = (T[:, :2] @ np.array([[0, 0], [W, 0], [W, H], [0, H]], float).T).T + T[:, 2]
    wkt = "POLYGON((" + ",".join(f"{x:.2f} {y:.2f}" for x, y in corners) + f",{corners[0][0]:.2f} {corners[0][1]:.2f}))"
    score = n_in / max(1, len(matches))
    return [Hypothesis(state.sheet.digest, tuple(float(v) for v in T.ravel()), wkt, ref.frame, score, "structure_match", (0,),
                       note=f"orb; inliers {n_in}/{len(matches)}; px->refpx {M.round(4).tolist()}")]


for p in (
    Primitive("edge_structure", "sheet-reader", True, (), "layer", "Canny edges of an image with no plates or text", edge_structure, "raster", requires=("opencv",)),
    Primitive("hint_area", "record-text", True, (), "candidate", "candidate area from a point / bbox hint in the record; none -> abstain later", hint_area, "raster"),
    Primitive("reference_render", "basemap", True, ("candidate",), "layer", "render reference line layers (roads, rail) of a GeoPackage over the candidate area on a metric grid", reference_render, "raster", requires=("a line GeoPackage with rtree indexes",)),
    Primitive("structure_match_orb", "basemap", True, ("layer",), "hypothesis", "ORB + RANSAC similarity of the sheet's structure mask vs the reference render; the generic baseline matcher", structure_match, "raster", requires=("opencv",)),
    Primitive("overlay_agreement", "basemap", True, ("hypothesis", "layer"), "evidence", "share of sheet structure within a few px of reference structure after the transform", overlay_agreement, "raster", requires=("opencv",)),
):
    register(p)
