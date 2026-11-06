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
    ("structure_overlay", "overlay_agreement is not None and overlay_agreement >= 0.6 and residual_within_bound is True", "accept"),
)
FACTS = ("places_in_footprint", "address_in_footprint", "matchers_agree", "editions_agree", "overlay_agreement", "residual_within_bound",
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


def execute_plan(plan: Plan, sheets: list[Sheet], trace_path: str | Path | None = None) -> tuple[list[State], list, list[str]]:
    reg, skipped = registry_for_plan(plan)
    order = [s.primitive for s in plan.recipe.steps if s.primitive in reg]
    dec = Decider(generic_policy(), None, lambda st: st.hypotheses[0].score if st.hypotheses else None)
    states, verdicts = [], []
    for sh in sheets:
        st = run(sh, reg, FixedPlan(order), trace_path)
        states.append(st); verdicts.append(dec.decide(st))
    return states, verdicts, skipped


def summary(state: State, verdict) -> dict:
    h = state.hypotheses[0] if state.hypotheses else None
    return {"sheet": state.sheet.id, "action": verdict.action, "why": verdict.why, "cues": len(state.cues), "candidates": len(state.candidates),
            "candidate_note": state.candidates[0].note[:120] if state.candidates else None,
            "hypothesis": {"matcher": h.matcher, "score": round(h.score, 3), "note": h.note[:160], "site_wkt": h.site_wkt[:200]} if h else None,
            "evidence": [{"name": e.name, "value": e.value, "family": e.family} for e in state.evidence],
            "steps": [(t["tool"], t.get("error") or t.get("skipped") or t.get("produced", "")) for t in state.trace],
            "cost": round(state.cost, 4), "seconds": round(state.seconds, 1)}
