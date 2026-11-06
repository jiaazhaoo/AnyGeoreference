"""Primitives bound to the planning-drawing pipeline (e2e-plan-extract, s3_georef). Imported lazily: the library
lists them everywhere; they run only where that repository and its data (OS Open Names, the address register, the
OS Zoomstack roads) exist. Each wrapper turns the pipeline's return values into loop objects and nothing else.

Pipeline line format (what its label rules and fits expect): {"text", "conf", "x", "y", "h"} with the centre and
height in sheet pixels. A Cue carries a bbox; the two are converted here."""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np

from ..model import Candidate, Cue, Hypothesis
from . import Primitive, register
from evalcore import Evidence

E2E = os.environ.get("E2E_REPO", "/env/code/e2e-plan-extract")


def _e2e():
    if E2E not in sys.path:
        sys.path.insert(0, E2E)
    from e2e_plan_extract.s3_georef import labels, plan, gazetteer, grid_ticks, names_locate, abp_local   # noqa: E402
    return labels, plan, gazetteer, grid_ticks, names_locate, abp_local


def _line(c: Cue) -> dict:
    x0, y0, x1, y1 = c.bbox
    return {"text": c.text, "conf": c.confidence, "x": (x0 + x1) / 2, "y": (y0 + y1) / 2, "h": max(1.0, y1 - y0)}


def _cue(state, l: dict, kind: str, reader: str) -> Cue:
    return Cue(state.sheet.digest, kind, l.get("name") or l["text"], (l["x"] - l["h"], l["y"] - l["h"] / 2, l["x"] + l["h"], l["y"] + l["h"] / 2),
               reader, float(l.get("conf", 1.0)))


# -- readers ---------------------------------------------------------------------------------------------------------
def ocr_cached(state):
    """Cached page OCR (the pipeline's stageA ocr_top3.jsonl): the page named in the sheet's meta, boxes rescaled from
    the OCR's working size to the page's pixel size. $0, no GPU; the live OCR primitive is `ocr_words`."""
    path, page = state.sheet.meta.get("ocr_jsonl"), state.sheet.meta.get("page")
    if not path or not os.path.exists(path):
        return []
    out = []
    for line in open(path):
        r = json.loads(line)
        if page and r.get("image") != page:
            continue
        ow, oh = r.get("ocr_size") or (None, None)
        W, H = state.sheet.meta.get("width"), state.sheet.meta.get("height")
        sx, sy = (W / ow, H / oh) if (ow and W) else (1.0, 1.0)
        for it in r["results"]:
            x0, y0, x1, y1 = it["bbox"]
            out.append(Cue(state.sheet.digest, "text", it["text"].strip(), (x0 * sx, y0 * sy, x1 * sx, y1 * sy), "ocr_cached", float(it.get("confidence", 1.0))))
    return out


def ocr_words(state, maxside: int = 2600):
    labels, *_ = _e2e()
    out = []
    for l in labels.dedup(labels.ocr_all(state.sheet.image, maxside=maxside)):
        out.append(_cue(state, l, "text", "ocr_words"))
    return out


def road_and_place_labels(state):
    """Road / place / number cues from the text cues, by the pipeline's label rules."""
    _, plan, *_ = _e2e()
    lines = [_line(c) for c in state.cues if c.kind == "text"]
    out = [_cue(state, lab, "road", "road_and_place_labels") for lab in plan.road_labels(lines)]
    out += [_cue(state, lab, "place", "road_and_place_labels") for lab in plan.place_labels(lines)]
    import re
    out += [_cue(state, l, "number", "road_and_place_labels") for l in lines if re.fullmatch(r"\d{1,3}[A-Za-z]?", l["text"])]
    return out


# -- retrieval -------------------------------------------------------------------------------------------------------
def _city(state):
    _, plan, _, _, names_locate, _ = _e2e()
    town_xy = tuple(state.sheet.meta.get("town_xy") or (435000.0, 387000.0))
    return names_locate.city_roads(town_xy, plan.roads_near), town_xy


def gazetteer_search(state, radius_m: float = 1500.0):
    """Record street + names read off the sheet -> an area from OS Open Names / the address register."""
    _, _, gazetteer, *_ = _e2e()
    city, town_xy = _city(state)
    address = state.sheet.record.get("address", "")
    phrases = gazetteer.phrases_of([c.text for c in state.cues if c.kind in ("road", "place", "text")])
    hit = gazetteer.locate(address, phrases, city, town_xy, state.sheet.meta.get("town", ""))
    if not hit:
        return []
    x, y, r = hit["x"], hit["y"], radius_m
    wkt = f"POLYGON(({x-r} {y-r},{x+r} {y-r},{x+r} {y+r},{x-r} {y+r},{x-r} {y-r}))"
    return [Candidate(state.sheet.digest, "gazetteer", wkt, "EPSG:27700", tuple(hit.get("hits", []))[:6], min(1.0, hit.get("cluster", 1) / 4),
                      note=f"street {hit.get('street')}")]


# -- matchers --------------------------------------------------------------------------------------------------------
def _sim6(T) -> tuple:
    """The pipeline's similarity (s, R, t) with w = s * (R @ [x, -y]) + t -> 6 affine coefficients."""
    s, R, t = float(T[0]), np.asarray(T[1], float), np.asarray(T[2], float)
    return (s * R[0, 0], -s * R[0, 1], t[0], s * R[1, 0], -s * R[1, 1], t[1])


def _footprint(state, T6) -> str:
    W, H = state.sheet.meta.get("width", 0), state.sheet.meta.get("height", 0)
    if not W or not H:
        return "POLYGON EMPTY"
    a, b, c, d, e, f = T6
    pts = [(a * x + b * y + c, d * x + e * y + f) for x, y in ((0, 0), (W, 0), (W, H), (0, H))]
    return "POLYGON((" + ",".join(f"{x:.2f} {y:.2f}" for x, y in pts) + f",{pts[0][0]:.2f} {pts[0][1]:.2f}))"


def grid_figures(state):
    """National-grid figures printed along the drawing's edges -> a similarity (the pipeline's grid_ticks.fit)."""
    _, _, _, grid_ticks, *_ = _e2e()
    lines = [_line(c) for c in state.cues if c.kind == "text"]
    near = None
    if state.candidates:
        import shapely.wkt
        g = shapely.wkt.loads(state.candidates[0].area_wkt); near = (g.centroid.x, g.centroid.y)
    r = grid_ticks.fit(lines, near)
    if not r:
        return []
    T6 = _sim6(r["T"])
    score = min(1.0, (r["n_e"] + r["n_n"]) / 8) * (1.0 / (1.0 + r["resid_m"] / 10))
    return [Hypothesis(state.sheet.digest, T6, _footprint(state, T6), "EPSG:27700", float(score), "grid_figures", (),
                       note=f"grid figures E{r['n_e']} N{r['n_n']}; resid {r['resid_m']:.1f} m; theta {r['theta']:.1f}; mpp {r['mpp']:.4f}")]


def text_anchor_fit(state, tol_m: float = 6.0, search_m: float = 16000.0):
    """House numbers x road names on the sheet -> address points from the local register -> RANSAC similarity."""
    labels, _, _, _, _, abp_local = _e2e()
    nums = [c for c in state.cues if c.kind == "number"]
    roads = sorted({c.text.upper() for c in state.cues if c.kind == "road"})
    if not nums or not roads:
        return []
    if state.candidates:
        import shapely.wkt
        x0, y0, x1, y1 = shapely.wkt.loads(state.candidates[0].area_wkt).bounds
        bbox = (x0 - 500, y0 - 500, x1 + 500, y1 + 500)
    else:
        tx, ty = tuple(state.sheet.meta.get("town_xy") or (435000.0, 387000.0))
        bbox = (tx - search_m, ty - search_m, tx + search_m, ty + search_m)
    anchors = []
    import re
    for n in nums:
        for road in roads:
            for r in abp_local.find(f"{n.text} {road.title()}", bbox, limit=10):
                if (r.get("BUILDING_NUMBER") or "").upper() == n.text.upper() and \
                        re.sub(r"[^A-Z ]", "", (r.get("THOROUGHFARE_NAME") or "").upper()) == road:
                    l = _line(n)
                    anchors.append({"label": f"{n.text} {road}", "px": (l["x"], l["y"]), "bng": (r["X_COORDINATE"], r["Y_COORDINATE"]), "addr": r["ADDRESS"]})
                    break
    if len(anchors) < 3:
        return []
    r = labels.ransac(anchors, tol_m=tol_m)
    if not r:
        return []
    T6 = _sim6(r["T"])
    return [Hypothesis(state.sheet.digest, T6, _footprint(state, T6), "EPSG:27700", float(len(r["inliers"]) / r["n_anchors"]), "text_anchor_fit",
                       (0,) if state.candidates else (), note=f"inliers {len(r['inliers'])}/{r['n_anchors']}; rms {r['rms_m']} m; mpp {r['m_per_px']}; rot {r['rotation_deg']}")]


# -- verification ----------------------------------------------------------------------------------------------------
def address_in_footprint(state):
    """The record's address, found in the local register, lies inside the best hypothesis' footprint; and how far it
    is from the footprint centre. Independent of every reader: the address register is its own family."""
    *_, abp_local = _e2e()
    if not state.hypotheses:
        return []
    import shapely.wkt
    fp = shapely.wkt.loads(state.hypotheses[0].site_wkt)
    if fp.is_empty:
        return []
    cx, cy = fp.centroid.x, fp.centroid.y
    hits = abp_local.find(state.sheet.record.get("address", ""), (cx - 5000, cy - 5000, cx + 5000, cy + 5000), limit=1)
    if not hits:
        return [Evidence("address_in_footprint", None, "deterministic", "address-register", note="address not found near the footprint")]
    from shapely.geometry import Point
    p = Point(hits[0]["X_COORDINATE"], hits[0]["Y_COORDINATE"])
    return [Evidence("address_in_footprint", bool(fp.contains(p)), "deterministic", "address-register", note=hits[0]["ADDRESS"][:80]),
            Evidence("address_to_centre_m", float(p.distance(fp.centroid)), "deterministic", "address-register")]


for p in (
    Primitive("ocr_cached", "sheet-reader", True, (), "cue", "cached page OCR from the pipeline's stageA (no GPU)", ocr_cached, "plans_gb"),
    Primitive("ocr_words", "sheet-reader", True, (), "cue", "OCR every word on the sheet with its pixel box", ocr_words, "plans_gb", requires=("e2e-plan-extract", "paddleocr")),
    Primitive("road_and_place_labels", "sheet-reader", True, ("cue",), "cue", "road / place / number cues from OCR text by the pipeline's label rules", road_and_place_labels, "plans_gb", requires=("e2e-plan-extract",)),
    Primitive("vlm_read_names", "sheet-reader", False, (), "cue", "a vision model reads road names and numbers (hosted; cached)", None, "plans_gb", cost_estimate=0.01, requires=("e2e-plan-extract", "OPENROUTER_API_KEY")),
    Primitive("gazetteer_search", "gazetteer", True, ("cue",), "candidate", "record street + sheet names -> an area from Open Names / the address register", gazetteer_search, "plans_gb", requires=("e2e-plan-extract", "OS Open Names", "OS Zoomstack")),
    Primitive("grid_figures", "geometry", True, ("cue",), "hypothesis", "national-grid figures along the edges -> similarity", grid_figures, "plans_gb", requires=("e2e-plan-extract",)),
    Primitive("text_anchor_fit", "geometry", True, ("cue",), "hypothesis", "house numbers x road names vs the local address register -> RANSAC similarity", text_anchor_fit, "plans_gb", requires=("e2e-plan-extract", "AddressBase Premium")),
    Primitive("address_in_footprint", "address-register", True, ("hypothesis",), "evidence", "the record's address point inside the best footprint; distance to its centre", address_in_footprint, "plans_gb", requires=("e2e-plan-extract", "AddressBase Premium")),
    Primitive("snap_faces", "geometry", True, ("hypothesis",), "evidence", "site polygon vs OS map faces (declared; the pipeline's step 13)", None, "plans_gb", requires=("e2e-plan-extract", "OS base map")),
):
    register(p)
