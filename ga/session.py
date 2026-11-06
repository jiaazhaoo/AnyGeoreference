"""Stepwise sessions: a run that an outside chooser (a person, Claude in a conversation, a web request handler)
advances one tool at a time across separate processes. The state is pickled between steps; every step appends to
the same trace a Planner would write, so a stepwise run and an in-process planner run are compared like for like."""
from __future__ import annotations

import json
import pickle
import time
from pathlib import Path

from .loop import State, step
from .model import Sheet
from .tools.registry import ToolRegistry


class StepSession:
    def __init__(self, dir: str | Path):
        self.dir = Path(dir); self.dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def start(cls, dir: str | Path, sheet: Sheet, kind: str) -> "StepSession":
        s = cls(dir)
        (s.dir / "meta.json").write_text(json.dumps({"kind": kind, "sheet": sheet.id, "started": time.time()}))
        s._save(State(sheet))
        return s

    def _save(self, state: State) -> None:
        with open(self.dir / "state.pkl", "wb") as f:
            pickle.dump(state, f)

    def load(self) -> State:
        with open(self.dir / "state.pkl", "rb") as f:
            return pickle.load(f)

    def kind(self) -> str:
        return json.loads((self.dir / "meta.json").read_text())["kind"]

    def options(self, registry: ToolRegistry) -> dict:
        """What the chooser sees: the state summary (no coordinates) and the runnable tools."""
        st = self.load()
        return {"state": st.summary(), "options": [registry[n].summary() for n in registry.runnable(st.present())]}

    def choose(self, registry: ToolRegistry, tool: str, why: str = "", chooser: str = "person") -> dict:
        st = self.load()
        st.trace.append({"tool": "planner", "chose": tool, "why": why, "chooser": chooser, "cost": 0.0, "seconds": 0.0})
        rec = step(st, registry, tool) if tool != "stop" else {"tool": "stop"}
        self._save(st)
        with open(self.dir / "choices.jsonl", "a") as f:
            f.write(json.dumps({"tool": tool, "why": why, "result": rec}, default=str) + "\n")
        return rec
