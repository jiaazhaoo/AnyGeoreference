"""matcher-toponym-constellation: place / landmark name cues matched against the gazetteer by the *shape* of their
pairwise distances. A similarity transform (rotation, scale, translation) does not change the ratio of two
distances, so three named points on the sheet and the same three names in the gazetteer either agree on that
ratio (and on a rotation) or they do not: every triple that agrees casts one vote for a (scale, rotation); the
densest vote cluster is the sheet's true pose, independent of any road or grid cue. See matcher-toponym-
constellation in the knowledge base."""
from __future__ import annotations

import itertools
import math
import os
import sqlite3
from collections import Counter, defaultdict

import numpy as np

from .. import Primitive, register
from ..generic import apply_transform, affine6, fit_transform
from ...model import Hypothesis
from evalcore import Evidence

DEFAULT_DB = "/data/reference/base-data/opname_csv_gb/os_open_names_uk.sqlite"


def _rot_diff(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def _sheet_points(state, name_kinds, min_text_len):
    """Cluster name cues by proximity: duplicate / re-read labels of the same name collapse to one point (the
    centroid of their boxes); different names, however close, stay distinct points."""
    groups: dict[str, list] = defaultdict(list)
    for c in state.cues:
        if c.kind not in name_kinds:
            continue
        t = c.text.strip()
        if len(t) < min_text_len:
            continue
        x0, y0, x1, y1 = c.bbox
        groups[t.lower()].append((t, (x0 + x1) / 2.0, (y0 + y1) / 2.0))
    pts = {}
    for items in groups.values():
        name = items[0][0]
        xs = [i[1] for i in items]
        ys = [i[2] for i in items]
        pts[name] = (sum(xs) / len(xs), sum(ys) / len(ys))
    return pts


def _gazetteer_hits(db: str, names, bbox):
    """Gazetteer hits for each sheet name, inside the candidate area's bounding box (the place_lookup area)."""
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


def toponym_constellation_fit(state, db: str | None = None, name_kinds=("place", "landmark"), min_names: int = 4,
                              min_consistent_triples: int = 5, ratio_tol: float = 0.08, scale_tol: float = 0.08,
                              rot_tol_deg: float = 8.0, ransac_tol_m: float = 250.0, min_text_len: int = 3):
    """Cluster the sheet's place/landmark name cues by proximity; for every triple of named points, vote for the
    (scale, rotation) that makes their pairwise pixel-distance ratios match the same triple of gazetteer hits
    carrying the same names inside the place_lookup candidate area. Keep the vote cluster with the most consistent
    triples (>= min_consistent_triples, else abstain). Seed a RANSAC similarity from the winning triples, score
    poses by inliers over every named point, refine the best pose by least squares on its inliers."""
    if not state.candidates:
        return []
    import shapely.wkt
    cand = next((c for c in state.candidates if c.source == "gazetteer"), state.candidates[0])
    area = shapely.wkt.loads(cand.area_wkt)
    if area.is_empty:
        return []
    bbox = area.bounds

    sheet_points = _sheet_points(state, name_kinds, min_text_len)
    if len(sheet_points) < min_names:
        state.evidence.append(Evidence("toponym_names_read", len(sheet_points), "deterministic", "gazetteer"))
        return []

    db = db or os.environ.get("E2E_OPEN_NAMES", DEFAULT_DB)
    gaz_hits = _gazetteer_hits(db, sheet_points, bbox)
    if len(gaz_hits) < min_names:
        state.evidence.append(Evidence("toponym_names_matched", len(gaz_hits), "deterministic", "gazetteer",
                                       note=f"of {len(sheet_points)} read, in the candidate area"))
        return []

    # -- vote: every triple of named points whose pixel-distance ratios match the same triple of gazetteer hits
    # casts one vote for a (scale, rotation); accumulate and keep the densest cluster.
    names = sorted(gaz_hits)
    triples = []
    for A, B, C in itertools.combinations(names, 3):
        pA, pB, pC = sheet_points[A], sheet_points[B], sheet_points[C]
        dAB, dAC, dBC = math.dist(pA, pB), math.dist(pA, pC), math.dist(pB, pC)
        if min(dAB, dAC, dBC) < 1e-6:
            continue
        for gA, gB, gC in itertools.product(gaz_hits[A], gaz_hits[B], gaz_hits[C]):
            mAB, mAC, mBC = math.dist(gA, gB), math.dist(gA, gC), math.dist(gB, gC)
            if min(mAB, mAC, mBC) < 1e-6:
                continue
            r1_px, r1_m = dAB / dBC, mAB / mBC
            r2_px, r2_m = dAC / dBC, mAC / mBC
            if abs(r1_px - r1_m) > ratio_tol * max(r1_px, r1_m) or abs(r2_px - r2_m) > ratio_tol * max(r2_px, r2_m):
                continue
            scale = (mAB / dAB + mAC / dAC + mBC / dBC) / 3.0
            rot = math.degrees(math.atan2(gB[1] - gA[1], gB[0] - gA[0])
                               - math.atan2(pB[1] - pA[1], pB[0] - pA[0])) % 360.0
            triples.append({"names": (A, B, C), "px": (pA, pB, pC), "m": (gA, gB, gC), "scale": scale, "rot": rot})

    if not triples:
        state.evidence.append(Evidence("toponym_consistent_triples", 0, "deterministic", "gazetteer"))
        return []

    clusters = []
    for t in triples:
        home = next((cl for cl in clusters if abs(t["scale"] - cl["scale"]) <= scale_tol * cl["scale"]
                     and _rot_diff(t["rot"], cl["rot"]) <= rot_tol_deg), None)
        if home is None:
            clusters.append({"scale": t["scale"], "rot": t["rot"], "items": [t]})
        else:
            home["items"].append(t)
    best = max(clusters, key=lambda cl: len(cl["items"]))
    if len(best["items"]) < min_consistent_triples:
        state.evidence.append(Evidence("toponym_consistent_triples", len(best["items"]), "deterministic", "gazetteer",
                                       note=f"need {min_consistent_triples}"))
        return []

    # -- the gazetteer point each winning triple proposes for a name; its mode is the name's correspondence
    proposals = defaultdict(list)
    for t in best["items"]:
        for nm, pm in zip(t["names"], t["m"]):
            proposals[nm].append(pm)
    correspond = {nm: Counter(pts).most_common(1)[0][0] for nm, pts in proposals.items()}
    names_all = sorted(correspond)
    src_all = np.array([sheet_points[nm] for nm in names_all], float)
    dst_all = np.array([correspond[nm] for nm in names_all], float)

    # -- RANSAC: seed a similarity from each winning triple, score by inliers over every named point
    best_fit = None
    for t in best["items"]:
        coeffs, _ = fit_transform(np.array(t["px"]), np.array(t["m"]), "similarity")
        resid = np.linalg.norm(apply_transform(coeffs, src_all, "similarity") - dst_all, axis=1)
        mask = resid <= ransac_tol_m
        n_in = int(mask.sum())
        key = (n_in, -float(resid[mask].sum()) if n_in else -1e18)
        if best_fit is None or key > best_fit[0]:
            best_fit = (key, mask)
    _, mask = best_fit
    if int(mask.sum()) < 3:
        return []

    # -- refine with all inlier pairs
    coeffs, res = fit_transform(src_all[mask], dst_all[mask], "similarity")
    rms_m = float(np.sqrt(np.mean(res ** 2))) if len(res) else 0.0
    n_in = int(mask.sum())

    W, H = state.sheet.meta.get("width", 0), state.sheet.meta.get("height", 0)
    if W and H:
        corners = apply_transform(coeffs, np.array([[0, 0], [W, 0], [W, H], [0, H]], float), "similarity")
        wkt = ("POLYGON((" + ",".join(f"{x:.2f} {y:.2f}" for x, y in corners)
               + f",{corners[0][0]:.2f} {corners[0][1]:.2f}))")
    else:
        wkt = "POLYGON EMPTY"
    score = min(1.0, n_in / 8.0) * (1.0 / (1.0 + rms_m / 100.0))
    note = (f"{len(best['items'])} consistent triples; {n_in}/{len(names_all)} name inliers; rms {rms_m:.1f} m; "
            f"scale {best['scale']:.4g}; rot {best['rot']:.1f} deg; names {names_all[:8]}")
    return [Hypothesis(state.sheet.digest, affine6(coeffs, "similarity"), wkt, cand.crs, float(score),
                       "toponym_constellation_fit", (state.candidates.index(cand),), note=note)]


register(Primitive("toponym_constellation_fit", "gazetteer", True, ("cue", "candidate"), "hypothesis",
                   "place/landmark name constellation vs the gazetteer: pairwise-distance-ratio voting picks the "
                   "scale/rotation, a RANSAC similarity seeded from the winning triples and refined on all inliers",
                   toponym_constellation_fit, "generated", requires=("OS Open Names",)))
