"""DECIDE: evidence -> policy -> calibrated probability -> accept / review / abstain. Thin over geo-eval."""
from __future__ import annotations

import os
import sys
from typing import Callable, Mapping

sys.path.insert(0, os.environ.get("GEO_EVAL_REPO", "/env/code/geo-eval"))
from evalcore import Calibrator, EvidenceSet, Policy      # noqa: E402

from .loop import State
from .model import ABSTAIN, Verdict


class Decider:
    def __init__(self, policy: Policy, calibrator: Calibrator | None, score_of: Callable[[State], float | None],
                 min_probability: float = 0.0):
        self.policy, self.calibrator, self.score_of, self.min_p = policy, calibrator, score_of, min_probability

    def facts(self, state: State) -> dict:
        es = EvidenceSet(state.evidence)
        f = es.facts()
        f.update({"n_hypotheses": len(state.hypotheses), "best_score": state.hypotheses[0].score if state.hypotheses else None,
                  "families": es.independent([e.name for e in state.evidence]), "cost": state.cost})
        return f

    def decide(self, state: State) -> Verdict:
        if not state.hypotheses:
            return Verdict(state.sheet.digest, None, None, ABSTAIN, "no placement hypothesis", tuple(t["tool"] for t in state.trace),
                           state.cost, state.seconds)
        out = self.policy.decide(self.facts(state))
        score = self.score_of(state)
        p = self.calibrator.prob(score) if (self.calibrator and score is not None) else None
        trail = tuple(t["tool"] for t in state.trace) + tuple(out.trail)
        if out.action != "accept" and out.action != "review":
            return Verdict(state.sheet.digest, None, None, ABSTAIN, out.why or "policy: no rule accepted", trail, state.cost, state.seconds)
        if p is not None and p < self.min_p:
            return Verdict(state.sheet.digest, None, None, ABSTAIN, f"probability {p:.2f} under {self.min_p}", trail, state.cost, state.seconds)
        return Verdict(state.sheet.digest, state.hypotheses[0], p if p is not None else 0.0, out.action, out.why, trail, state.cost, state.seconds)
