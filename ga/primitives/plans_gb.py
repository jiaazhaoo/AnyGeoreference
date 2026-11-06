"""Primitives bound to the planning-drawing pipeline (e2e-plan-extract, s3_georef / s4_verify). Imported lazily:
the library lists them everywhere; they run only where that repository and its data (OS base maps, address
register) exist. Each wrapper turns the pipeline's return values into loop objects and nothing else."""
from __future__ import annotations

import os
import sys

from ..model import Candidate, Cue, Hypothesis, Layer
from . import Primitive, register
from evalcore import Evidence

E2E = os.environ.get("E2E_REPO", "/env/code/e2e-plan-extract")


def _e2e():
    if E2E not in sys.path:
        sys.path.insert(0, E2E)
    from e2e_plan_extract.s3_georef import labels, plan, gazetteer, grid_ticks   # noqa: E402
    return labels, plan, gazetteer, grid_ticks


def ocr_words(state, maxside: int = 2600):
    labels, *_ = _e2e()
    lines = labels.dedup(labels.ocr_all(state.sheet.image, maxside=maxside))
    out = []
    for ln in lines:                                   # pipeline lines: dicts with 'text' and a pixel box
        box = ln.get("box") or ln.get("bbox")
        if not box:
            continue
        xs = [p[0] for p in box] if isinstance(box[0], (list, tuple)) else [box[0], box[2]]
        ys = [p[1] for p in box] if isinstance(box[0], (list, tuple)) else [box[1], box[3]]
        out.append(Cue(state.sheet.digest, "text", ln["text"], (min(xs), min(ys), max(xs), max(ys)), "ocr_words",
                       float(ln.get("conf", 1.0))))
    return out


def road_and_place_labels(state):
    """Split OCR text cues into road / place / number cues with the pipeline's label rules."""
    _, plan, *_ = _e2e()
    lines = [{"text": c.text, "box": [(c.bbox[0], c.bbox[1]), (c.bbox[2], c.bbox[1]), (c.bbox[2], c.bbox[3]), (c.bbox[0], c.bbox[3])]}
             for c in state.cues if c.kind == "text"]
    out = []
    for lab in plan.road_labels(lines):
        out.append(Cue(state.sheet.digest, "road", lab["text"], _box(lab), "road_and_place_labels"))
    for lab in plan.place_labels(lines):
        out.append(Cue(state.sheet.digest, "place", lab["text"], _box(lab), "road_and_place_labels"))
    return out


def _box(lab) -> tuple:
    b = lab.get("box") or lab.get("bbox")
    xs = [p[0] for p in b]; ys = [p[1] for p in b]
    return (min(xs), min(ys), max(xs), max(ys))


def grid_figures(state):
    """National-grid figures printed on the drawing -> grid cues 'easting,northing' at their pixel."""
    _, _, _, grid_ticks = _e2e()
    lines = [{"text": c.text, "box": [(c.bbox[0], c.bbox[1]), (c.bbox[2], c.bbox[3])]} for c in state.cues if c.kind == "text"]
    T = grid_ticks.fit(lines)
    if not T:
        return []
    out = []
    for px, (e, n) in grid_ticks.agree(lines, T) or []:
        out.append(Cue(state.sheet.digest, "grid", f"{e},{n}", (px[0] - 1, px[1] - 1, px[0] + 1, px[1] + 1), "grid_figures"))
    return out


def gazetteer_search(state, radius_m: float = 1500.0):
    """Record street + names read off the sheet -> candidate areas from Open Names / the address register."""
    _, _, gazetteer, _ = _e2e()
    address = state.sheet.record.get("address", "")
    phrases = gazetteer.phrases_of([c.text for c in state.cues if c.kind in ("road", "place", "text")])
    city = state.sheet.meta.get("city") or {}
    hit = gazetteer.locate(address, phrases, city, state.sheet.meta.get("town_xy"), state.sheet.meta.get("town", ""))
    if not hit:
        return []
    x, y = hit["x"], hit["y"]; r = radius_m
    wkt = f"POLYGON(({x-r} {y-r},{x+r} {y-r},{x+r} {y+r},{x-r} {y+r},{x-r} {y-r}))"
    return [Candidate(state.sheet.digest, "gazetteer", wkt, "EPSG:27700", tuple(hit.get("names", [])), float(hit.get("score", 0.5)),
                      note=hit.get("why", ""))]


def text_anchor_fit(state, tol_m: float = 6.0):
    """House-number / road-name anchors against the register -> RANSAC similarity -> hypotheses."""
    labels, plan, *_ = _e2e()
    lines = [{"text": c.text, "box": [(c.bbox[0], c.bbox[1]), (c.bbox[2], c.bbox[3])]} for c in state.cues if c.kind in ("text", "number", "road")]
    roads = [c.text for c in state.cues if c.kind == "road"]
    near = None
    if state.candidates:
        near = state.candidates[0].area_wkt
    anchors = labels.number_anchors(lines, roads, state.sheet.meta.get("town", ""), os.environ.get("OS_API_KEY", ""), near=near)
    if not anchors:
        return []
    T, inl = labels.ransac(anchors, tol_m=tol_m)
    if T is None:
        return []
    a, b, c, d, e, f = (T[0][0], T[0][1], T[0][2], T[1][0], T[1][1], T[1][2])
    return [Hypothesis(state.sheet.digest, (a, b, c, d, e, f), "POLYGON EMPTY", "EPSG:27700", float(len(inl)) / max(1, len(anchors)),
                       "text_anchor_fit", (0,) if state.candidates else (), note=f"inliers {len(inl)}/{len(anchors)}")]


def snap_faces(state):
    """Best hypothesis' site polygon against OS map faces and the address point (s4_verify.qa_input_polygon)."""
    sys.path.insert(0, E2E)
    from e2e_plan_extract.s4_verify import qa_input_polygon as qip   # noqa: E402
    if not state.hypotheses:
        return []
    r = qip.check(state.hypotheses[0].site_wkt, state.sheet.record, state.sheet.meta)   # adapter-side contract
    return [Evidence("snap_iou", float(r.get("snap_iou") or 0.0), "deterministic", "geometry"),
            Evidence("address_inside", bool(r.get("address_in_input")), "deterministic", "address-register"),
            Evidence("site_iou", float(r.get("site_iou") or 0.0), "deterministic", "address-register")]


for p in (
    Primitive("ocr_words", "sheet-reader", True, (), "cue", "OCR every word on the sheet with its pixel box", ocr_words, "plans_gb", requires=("e2e-plan-extract", "paddleocr")),
    Primitive("road_and_place_labels", "sheet-reader", True, ("cue",), "cue", "road / place cues from OCR text by the pipeline's label rules", road_and_place_labels, "plans_gb", requires=("e2e-plan-extract",)),
    Primitive("grid_figures", "sheet-reader", True, ("cue",), "cue", "national-grid figures on the sheet -> grid cues", grid_figures, "plans_gb", requires=("e2e-plan-extract",)),
    Primitive("vlm_read_names", "sheet-reader", False, (), "cue", "a vision model reads road names and numbers (hosted; cached)", None, "plans_gb", cost_estimate=0.01, requires=("e2e-plan-extract", "OPENROUTER_API_KEY")),
    Primitive("gazetteer_search", "gazetteer", True, ("cue",), "candidate", "record street + sheet names -> an area from Open Names / address register", gazetteer_search, "plans_gb", requires=("e2e-plan-extract", "OS Open Names")),
    Primitive("text_anchor_fit", "geometry", True, ("cue",), "hypothesis", "house-number / road anchors vs the register -> RANSAC similarity", text_anchor_fit, "plans_gb", requires=("e2e-plan-extract", "OS Places")),
    Primitive("snap_faces", "geometry", True, ("hypothesis",), "evidence", "site polygon vs OS map faces, address point inside", snap_faces, "plans_gb", requires=("e2e-plan-extract", "OS base map")),
):
    register(p)
