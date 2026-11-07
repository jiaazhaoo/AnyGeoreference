"""The plan a main agent writes for a batch of one to three similar sheets: a recipe over the primitive library,
where truth will come from and how far it is trusted, the evaluation it will run, the stop rules, the budget, and
what it could not compose (missing primitives). Validated composition-only; a plan without a truth source above
self-consistency can only deliver "unverified"."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Callable, Mapping

from .primitives import LIBRARY
from .recipe import AdapterSpec, Step

TRUTH_RANK = {"user_control_points": 4, "external_authority": 3, "batch_agreement": 2, "self_consistency": 1}

SYSTEM = """You are the main agent of a georeferencing system. You receive the profile of a batch of one to three
similar scanned maps (what a reader found on them), retrieved knowledge about how such maps are georeferenced, and
the library of primitives you may compose. Write the plan as one JSON object:
{"recipe": [{"primitive": "<library name>", "params": {...}}, ...],
 "truth_sources": [{"kind": "user_control_points|external_authority|batch_agreement|self_consistency", "how": "<one sentence>", "trust": 0..1}],
 "evaluation": {"metrics": ["placed_right", "placed_wrong", "abstained", "calibration", "cost"], "tolerance_m": <number>, "split": "<how the sheets are used: pilot / check>"},
 "stop_rules": {"accept_when": "<condition in words>", "abstain_when": "<condition>", "max_cost_usd": <number>, "max_minutes_per_sheet": <number>},
 "missing_primitives": [{"name": "<snake_case name>", "why": "<one sentence>", "consumes": ["cue"|"candidate"|"hypothesis"|"layer"], "produces": "cue|candidate|hypothesis|evidence|layer", "family": "<evidence family>", "method": "<how it computes its output, in 3-6 sentences, concrete enough to implement from>"}],
 "risks": ["<one sentence each>"],
 "why": "<three sentences: the method, the second evidence family, what one sheet alone cannot give>"}
Rules: a step's params are ONLY names listed in that primitive's "params" (anything else is dropped); leave params
at the primitive's defaults unless the knowledge or a measured result gives a reason, and never set data paths
(db, gpkg): the defaults were tuned on real sheets and a guessed value usually breaks a step that would have worked; keep the whole
answer under 8000 characters; the model only reads (cues); coordinates come from deterministic matchers; accept needs a second evidence
family independent of the reader; abstain is an answer; use only library names in the recipe; with one sheet there is
no batch agreement; with three similar sheets pilot on one and check on the others. When the knowledge describes a
method the library has no primitive for, do not drop the method: put it in missing_primitives with a concrete
`method` so it can be built, and put its name in the recipe at the step where it belongs; a missing capability that
is known to be buildable is built, not abstained on."""


REVISE = """You are the main agent of a georeferencing system, revising your plan after running it. You receive the plan you
wrote, the library (with each primitive's params), and what happened per sheet: the steps run, what each produced,
the evidence with its values and notes, the decision and its reason. Decide one of: {"action": "stop", "why": "..."}
when the result is final (accepted with a second family, or an honest abstention nothing in the library or knowledge
can change); or {"action": "revise", "why": "...", "recipe": [...same form as before...], "missing_primitives": [...]}
when a different step, a different parameter inside a primitive's contract, or a primitive still missing would
change the outcome. Revise only on evidence: an evidence note saying "need 5" with 3 found is a parameter to
reconsider if the knowledge allows; a reader that found no bounds is a step to add; a tool that produced 0 is a tool
to replace, not to repeat. When a step produced 0 with params you set, first try it at its defaults. Never lower a verification threshold to make an accept; a revision that only changes the
accept rule is refused. Keep the answer under 6000 characters; params only from the contract."""


@dataclass
class Plan:
    recipe: AdapterSpec
    truth_sources: list[dict]
    evaluation: dict
    stop_rules: dict
    missing_primitives: list[dict] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    why: str = ""
    n_sheets: int = 1

    def best_truth(self) -> str:
        kinds = [t.get("kind", "self_consistency") for t in self.truth_sources]
        return max(kinds, key=lambda k: TRUTH_RANK.get(k, 0)) if kinds else "self_consistency"

    def can_accept(self) -> bool:
        return TRUTH_RANK.get(self.best_truth(), 0) >= 2

    def problems(self) -> list[str]:
        out = []
        bad = self.recipe.validate(set(LIBRARY))
        if bad:
            out.append(f"not in the library: {bad}")
        kinds_out = {LIBRARY[s.primitive].produces for s in self.recipe.steps if s.primitive in LIBRARY}
        if "hypothesis" not in kinds_out:
            out.append("no matcher: nothing produces a hypothesis")
        if "evidence" not in kinds_out:
            out.append("no verification: nothing produces evidence")
        for st in self.recipe.steps:
            if st.primitive in LIBRARY and LIBRARY[st.primitive].available():
                unk = LIBRARY[st.primitive].unknown_params(dict(st.params))
                if unk:
                    out.append(f"{st.primitive}: params not in its contract, dropped at run time: {unk}")
        if self.n_sheets == 1 and any(t.get("kind") == "batch_agreement" for t in self.truth_sources):
            out.append("batch agreement claimed for a single sheet")
        if not self.can_accept():
            out.append("truth is self-consistency only: deliveries are unverified")
        return out

    def to_dict(self) -> dict:
        d = asdict(self); d["recipe"] = {"steps": [asdict(s) for s in self.recipe.steps]}
        d["best_truth"] = self.best_truth(); d["can_accept"] = self.can_accept(); d["problems"] = self.problems()
        return d


def library_summary() -> list[dict]:
    return [{"name": p.name, "consumes": list(p.consumes), "produces": p.produces, "family": p.family, "deterministic": p.deterministic,
             "cost": p.cost_estimate, "about": p.about, "implemented": p.available(), "params": sorted(p.accepted_params())} for p in LIBRARY.values()]


def _steps(recipe) -> tuple[Step, ...]:
    """Recipe items as the agent wrote them: dicts keyed primitive / name / tool, or bare names."""
    out = []
    if isinstance(recipe, dict):                                   # {"steps": [...]} as the plan's own to_dict prints it
        recipe = recipe.get("steps", [])
    for s in recipe if isinstance(recipe, list) else []:
        if isinstance(s, str):
            out.append(Step(s, {}))
        elif isinstance(s, dict):
            nm = s.get("primitive") or s.get("name") or s.get("tool") or ""
            params = s.get("params") if isinstance(s.get("params"), dict) else {}
            if nm:
                out.append(Step(str(nm), dict(params)))
    return tuple(out)


def _missing(items) -> list[dict]:
    return [m if isinstance(m, dict) else {"name": str(m)} for m in (items if isinstance(items, list) else [])]


def make_plan(profile: Mapping, knowledge: str, n_sheets: int, ask: Callable[[str, str], dict]) -> tuple[Plan, dict]:
    user = json.dumps({"n_sheets": n_sheets, "profile": profile, "knowledge": knowledge, "library": library_summary()}, ensure_ascii=False)
    a = ask(SYSTEM, user)
    plan = Plan(AdapterSpec("planned", _steps(a.get("recipe", [])), (), "lib-v0"), list(a.get("truth_sources", [])), dict(a.get("evaluation", {})),
                dict(a.get("stop_rules", {})), _missing(a.get("missing_primitives", [])), list(a.get("risks", [])), str(a.get("why", "")), n_sheets)
    return plan, a


def revise_plan(plan: Plan, results: list[dict], ask: Callable[[str, str], dict]) -> tuple[Plan | None, dict]:
    """The improvement loop's one step: the main agent sees what its plan did and either stops or revises the recipe."""
    user = json.dumps({"plan": plan.to_dict(), "results": results, "library": library_summary()}, ensure_ascii=False, default=str)
    a = ask(REVISE, user)
    steps = _steps(a.get("recipe", []))
    if a.get("action") != "revise" or not steps:
        return None, a
    new = Plan(AdapterSpec("revised", steps, (), "lib-v0"), plan.truth_sources, plan.evaluation, plan.stop_rules,
               _missing(a.get("missing_primitives", [])), plan.risks, str(a.get("why", "")), plan.n_sheets)
    return new, a
