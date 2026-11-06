"""Primitives for the third kind: a raster with no usable text (aerial / satellite tile, an unlabelled map extract).
Only structure is available: linework or edges on the image, matched against rendered reference vectors over a
candidate area that must come from somewhere else (the record, a user hint, a coarse geocode). With no candidate
area the loop abstains, by design."""
from __future__ import annotations

import numpy as np

from ..model import Candidate, Layer
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
    a, b, c, d, e, f = state.hypotheses[0].transform
    M = np.array([[a, b, c], [d, e, f]], float)
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


for p in (
    Primitive("edge_structure", "sheet-reader", True, (), "layer", "Canny edges of an image with no plates or text", edge_structure, "raster", requires=("opencv",)),
    Primitive("hint_area", "record-text", True, (), "candidate", "candidate area from a point / bbox hint in the record; none -> abstain later", hint_area, "raster"),
    Primitive("reference_render", "basemap", True, ("candidate",), "layer", "render reference vectors (roads, rail, water) for the candidate area on a metric grid", None, "raster", requires=("OS / OSM vectors",)),
    Primitive("overlay_agreement", "basemap", True, ("hypothesis", "layer"), "evidence", "share of sheet structure within a few px of reference structure after the transform", overlay_agreement, "raster", requires=("opencv",)),
):
    register(p)
