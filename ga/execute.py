"""EXECUTE a plan: the main agent's recipe (ga/plan.py) run through the loop on each sheet of the batch, with the
generic two-family policy deciding. The generic policy is the floor every kind's policy refines: a hypothesis is
accepted only when a family the matcher did not use agrees with it; a hypothesis alone is a review; none is an
abstention. Missing primitives named by the plan are built first (ga/builder.py) and loaded from generated/."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.environ.get("GEO_EVAL_REPO", "/env/code/geo-eval"))
from evalcore import Policy, Rule          # noqa: E402

from .decide import Decider
from .loop import FixedPlan, State, run
from .model import Sheet
from .plan import Plan
from .primitives import LIBRARY, load_generated
from .tools.registry import ToolRegistry

SECOND_FAMILY = (
    ("places_inside", "places_in_footprint is not None and places_in_footprint >= 2", "accept"),
    ("address_inside", "address_in_footprint is True", "accept"),
    ("matchers_agree", "matchers_agree is True", "accept"),
    ("editions_agree", "editions_agree is True", "accept"),
    ("batch_agrees", "batch_agreement is True", "accept"),
    ("structure_overlay", "overlay_agreement is not None and overlay_agreement >= 0.6 and residual_within_bound is True", "accept"),
)
FACTS = ("batch_agreement", "places_in_footprint", "address_in_footprint", "matchers_agree", "editions_agree", "overlay_agreement", "residual_within_bound",
         "best_score", "best_matcher", "n_location_cues", "n_candidates", "families", "n_hypotheses", "places_found", "road_fit_inliers")


def generic_policy() -> Policy:
    rules = []
    for rid, expr, to in SECOND_FAMILY:
        rules.append(Rule(rid, (lambda f, e=expr: bool(eval(e, {}, {**{k: None for k in FACTS}, **f}))), to, when_text=expr))
    return Policy("generic-two-family", "v0", rules, default="review")


def registry_for_plan(plan: Plan) -> tuple[ToolRegistry, list[str]]:
    """Tools for the plan's recipe, in order: library primitives (including generated ones) with the plan's params;
    unavailable or unknown primitives are listed, not fatal, so the rest of the recipe still runs."""
    load_generated()
    reg, skipped = ToolRegistry(), []
    for s in plan.recipe.steps:
        p = LIBRARY.get(s.primitive)
        if p is None:
            skipped.append(f"{s.primitive}: not in the library"); continue
        if s.primitive in reg:
            continue
        if not p.available():
            skipped.append(f"{s.primitive}: declared, not implemented here ({p.requires})"); continue
        reg.add(p.tool(**dict(s.params)))
    return reg, skipped


def _sibling_candidate(state: State, placed: State, radius_m: float = 3000.0):
    """A batch's sheets are similar and adjacent: a sheet that found no area searches round a placed sibling's footprint."""
    import shapely.wkt
    from .model import Candidate
    g = shapely.wkt.loads(placed.hypotheses[0].site_wkt).centroid
    x, y, r = g.x, g.y, radius_m
    wkt = f"POLYGON(({x-r} {y-r},{x+r} {y-r},{x+r} {y+r},{x-r} {y+r},{x-r} {y-r}))"
    return Candidate(state.sheet.digest, "batch-sibling", wkt, placed.hypotheses[0].crs, (placed.sheet.id,), 0.5,
                     note=f"round the placed sibling {placed.sheet.id}")


def execute_plan(plan: Plan, sheets: list[Sheet], trace_path: str | Path | None = None, share_area: bool = True) -> tuple[list[State], list, list[str]]:
    reg, skipped = registry_for_plan(plan)
    order = [s.primitive for s in plan.recipe.steps if s.primitive in reg]
    dec = Decider(generic_policy(), None, lambda st: st.hypotheses[0].score if st.hypotheses else None)
    states = [run(sh, reg, FixedPlan(order), trace_path) for sh in sheets]
    placed = [st for st in states if st.hypotheses]
    if share_area and placed and len(states) > 1:
        for i, st in enumerate(states):
            if st.hypotheses:
                continue
            seeded = State(st.sheet)
            seeded.candidates.append(_sibling_candidate(seeded, placed[0]))
            seeded.trace.append({"tool": "sibling_area", "produced": 1, "kind": "candidate", "cost": 0.0, "seconds": 0.0})
            states[i] = FixedPlan(order).drive(seeded, reg)
    batch_agreement(states)
    verdicts = [dec.decide(st) for st in states]
    return states, verdicts, skipped


def _pose(h):
    """Scale (CRS units per px) and rotation (deg) of a hypothesis' affine part."""
    import math
    a, b, c, d, e, f = h.transform
    return math.hypot(a, d), math.degrees(math.atan2(d, a)) % 360


def batch_agreement(states: list[State], scale_tol: float = 0.05, rot_tol: float = 3.0, seam_tol: float = 0.2) -> None:
    """The batch's own second family (knowledge: verify-neighbour-sheets). Sheets of one batch placed independently,
    from different labels, must agree on scale and rotation, and adjoining sheets must meet edge to edge: the offset
    between two placements, taken back into one sheet's pixel frame, is about one sheet width or height along one
    axis. Each placed sheet gets Evidence batch_agreement True when at least one sibling agrees on all three, with
    the numbers in the note; False when siblings were placed and none agrees; nothing when it has no placed sibling."""
    import math
    from evalcore import Evidence
    placed = [st for st in states if st.hypotheses]
    if len(placed) < 2:
        return
    for st in placed:
        ha = st.hypotheses[0]; sa, ra = _pose(ha)
        a, b, c, d, e, f = ha.transform
        det = a * e - b * d
        best = None
        for other in placed:
            if other is st:
                continue
            hb = other.hypotheses[0]; sb, rb = _pose(hb)
            ds = abs(sa - sb) / max(sa, sb); dr = min(abs(ra - rb), 360 - abs(ra - rb))
            # where does the other sheet's origin fall in this sheet's pixel frame?
            ox, oy = hb.transform[2] - c, hb.transform[5] - f
            px, py = (e * ox - b * oy) / det, (-d * ox + a * oy) / det
            w, h = st.sheet.meta.get("width") or 1, st.sheet.meta.get("height") or 1
            along_x = abs(abs(px) / w - 1) <= seam_tol and abs(py) / h <= seam_tol
            along_y = abs(abs(py) / h - 1) <= seam_tol and abs(px) / w <= seam_tol
            ok = ds <= scale_tol and dr <= rot_tol and (along_x or along_y)
            rec = (ok, other.sheet.id, ds, dr, px / w, py / h)
            if best is None or (ok and not best[0]):
                best = rec
        ok, oid, ds, dr, fx, fy = best
        st.evidence.append(Evidence("batch_agreement", bool(ok), "deterministic", "batch",
                                    note=f"vs {oid}: scale differs {ds:.1%}, rotation {dr:.1f} deg, sibling origin at ({fx:+.2f} w, {fy:+.2f} h) in this sheet's frame"))


def summary(state: State, verdict) -> dict:
    h = state.hypotheses[0] if state.hypotheses else None
    return {"sheet": state.sheet.id, "action": verdict.action, "why": verdict.why, "cues": len(state.cues), "candidates": len(state.candidates),
            "candidate_note": state.candidates[0].note[:120] if state.candidates else None,
            "hypothesis": {"matcher": h.matcher, "score": round(h.score, 3), "note": h.note[:160], "site_wkt": h.site_wkt[:200]} if h else None,
            "evidence": [{"name": e.name, "value": e.value, "family": e.family} for e in state.evidence],
            "steps": [(t["tool"], t.get("error") or t.get("skipped") or t.get("produced", "")) for t in state.trace],
            "cost": round(state.cost, 4), "seconds": round(state.seconds, 1)}
