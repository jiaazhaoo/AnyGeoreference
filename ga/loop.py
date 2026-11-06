"""The loop: a State, two drivers (FixedPlan, Planner), one trace format. Both drivers call the same tools."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from .model import Candidate, Cue, Hypothesis, Layer, Sheet
from .tools.registry import ToolRegistry


@dataclass
class State:
    sheet: Sheet
    cues: list[Cue] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    evidence: list = field(default_factory=list)          # evalcore.Evidence
    layers: list[Layer] = field(default_factory=list)
    trace: list[dict] = field(default_factory=list)
    cost: float = 0.0
    seconds: float = 0.0

    def present(self) -> set[str]:
        out = set()
        if self.cues: out.add("cue")
        if self.candidates: out.add("candidate")
        if self.hypotheses: out.add("hypothesis")
        if self.evidence: out.add("evidence")
        if self.layers: out.add("layer")
        return out

    def summary(self) -> dict:
        """What a planner is allowed to see: counts and scores, never coordinates."""
        return {"sheet": self.sheet.id, "kind": self.sheet.kind,
                "cues": [{"kind": c.kind, "text": c.text, "confidence": c.confidence} for c in self.cues],
                "candidates": [{"source": c.source, "answers": list(c.answers), "score": c.score} for c in self.candidates],
                "hypotheses": [{"matcher": h.matcher, "score": h.score} for h in self.hypotheses],
                "evidence": [{"name": e.name, "value": e.value, "family": e.family} for e in self.evidence],
                "layers": [{"name": l.name, "kind": l.kind, "frame": l.frame} for l in self.layers],
                "cost": round(self.cost, 4), "steps": [t["tool"] for t in self.trace]}

    def layer(self, name: str) -> Layer | None:
        return next((l for l in reversed(self.layers) if l.name == name), None)

    def add(self, kind: str, objs: Iterable) -> int:
        objs = list(objs)
        target = {"cue": self.cues, "candidate": self.candidates, "hypothesis": self.hypotheses, "evidence": self.evidence,
                  "layer": self.layers}[kind]
        target.extend(objs)
        if kind == "hypothesis":
            self.hypotheses.sort(key=lambda h: h.score, reverse=True)
        return len(objs)


def step(state: State, registry: ToolRegistry, name: str) -> dict:
    """Run one tool, append its trace line, return it. A tool whose inputs are missing is recorded as skipped."""
    t = registry[name]
    if not set(t.consumes) <= state.present():
        rec = {"tool": name, "skipped": f"needs {t.consumes}", "cost": 0.0, "seconds": 0.0}
        state.trace.append(rec)
        return rec
    t0 = time.time()
    try:
        objs = t.run(state)
    except Exception as e:                                                        # noqa: BLE001  a failing tool is a fact in the trace, not the end of the sheet
        rec = {"tool": name, "error": f"{type(e).__name__}: {str(e)[:200]}", "produced": 0, "kind": t.produces, "cost": 0.0, "seconds": round(time.time() - t0, 3)}
        state.trace.append(rec)
        return rec
    n = state.add(t.produces, objs)
    rec = {"tool": name, "produced": n, "kind": t.produces, "cost": t.cost_estimate if not t.deterministic else 0.0,
           "seconds": round(time.time() - t0, 3)}
    state.cost += rec["cost"]
    state.seconds += rec["seconds"]
    state.trace.append(rec)
    return rec


class FixedPlan:
    """The production baseline: an ordered list of tool names, every one attempted."""
    def __init__(self, plan: Iterable[str]):
        self.plan = list(plan)

    def drive(self, state: State, registry: ToolRegistry) -> State:
        for name in self.plan:
            step(state, registry, name)
        return state


class Planner:
    """An LLM (or any chooser) picks the next tool from the registry given the state summary. Bounded."""
    def __init__(self, choose: Callable[[dict, list[dict]], str], max_steps: int = 12, max_cost: float = 0.5):
        self.choose, self.max_steps, self.max_cost = choose, max_steps, max_cost

    def drive(self, state: State, registry: ToolRegistry) -> State:
        for _ in range(self.max_steps):
            runnable = registry.runnable(state.present())
            options = [registry[n].summary() for n in runnable]
            choice = self.choose(state.summary(), options)
            state.trace.append({"tool": "planner", "chose": choice, "cost": 0.0, "seconds": 0.0})
            if choice == "stop" or choice not in registry:
                break
            if state.cost + registry[choice].cost_estimate > self.max_cost:
                state.trace.append({"tool": "planner", "stopped": "cost cap", "cost": 0.0, "seconds": 0.0})
                break
            step(state, registry, choice)
        return state


def run(sheet: Sheet, registry: ToolRegistry, driver, trace_path: str | Path | None = None) -> State:
    state = driver.drive(State(sheet), registry)
    if trace_path:
        with open(trace_path, "a") as f:
            f.write(json.dumps({"sheet": sheet.id, "digest": sheet.digest, "trace": state.trace, "cost": state.cost,
                                "seconds": state.seconds, "driver": type(driver).__name__}) + "\n")
    return state
