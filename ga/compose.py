"""Level 2, step Compose: from a Profile and the primitive library, an agent proposes a recipe (an ordered
composition of primitives with parameters). The proposal is validated composition-only and compared with the
kind's human-written spec, so "can an agent compose the recipe a person wrote from the same library" is a number:
primitive-set Jaccard, order agreement, and what it left out or added. The chooser is any callable (an LLM through
the planner's chooser interface, or a replayed cache); no call is made without one."""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Callable

from .primitives import LIBRARY
from .recipe import AdapterSpec, Profile, Step

SYSTEM = """You compose a georeferencing recipe for one kind of scanned map from a library of primitives. Each
primitive declares what it consumes and produces (cue, candidate, hypothesis, evidence, layer), its evidence family,
whether it is deterministic and its cost. Rules: the model may only read (cues); coordinates come from deterministic
matchers; every placement must be verified by evidence from a family independent of the reader; abstaining is an
answer, so include at least one verification. Given the profile of the kind, answer with one JSON object:
{"steps": [{"primitive": "<name>", "params": {...}}, ...], "why": "<two sentences>"} using only library names, in
execution order, no more than 10 steps."""


def library_summary() -> list[dict]:
    return [{"name": p.name, "consumes": list(p.consumes), "produces": p.produces, "family": p.family,
             "deterministic": p.deterministic, "cost": p.cost_estimate, "about": p.about} for p in LIBRARY.values()]


def compose(profile: Profile, ask: Callable[[list[dict]], dict], kind_name: str = "proposed") -> tuple[AdapterSpec, dict]:
    """ask(messages) -> parsed JSON answer. Returns the spec (validated names only) and the raw answer."""
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": json.dumps({"profile": asdict(profile), "library": library_summary()}, ensure_ascii=False)}]
    answer = ask(messages)
    steps = tuple(Step(s.get("primitive", ""), dict(s.get("params", {}))) for s in answer.get("steps", []) if isinstance(s, dict))
    spec = AdapterSpec(kind_name, steps, (), "lib-v0")
    return spec, answer


def compare(proposed: AdapterSpec, human: AdapterSpec) -> dict:
    """How close the agent's composition is to the person's: set overlap, order agreement on the shared steps,
    what is missing, what is extra, and whether the proposal is composition-only."""
    a = [s.primitive for s in proposed.steps]; b = [s.primitive for s in human.steps]
    sa, sb = set(a), set(b)
    shared = [x for x in b if x in sa]
    order_a = [x for x in a if x in sb]
    pairs = [(x, y) for i, x in enumerate(shared) for y in shared[i + 1:]]
    agree = sum(1 for x, y in pairs if order_a.index(x) < order_a.index(y)) if pairs else 0
    kinds_covered = {LIBRARY[x].produces for x in sa if x in LIBRARY}
    return {"jaccard": round(len(sa & sb) / max(1, len(sa | sb)), 3), "shared": len(sa & sb), "missing": sorted(sb - sa), "extra": sorted(sa - sb),
            "order_agreement": round(agree / len(pairs), 3) if pairs else None, "invalid": proposed.validate(set(LIBRARY)),
            "has_verification": "evidence" in kinds_covered, "has_matcher": "hypothesis" in kinds_covered, "n_steps": len(a)}
