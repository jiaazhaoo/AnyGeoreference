"""Tools: declared callables both drivers can see. A tool consumes object kinds and produces one kind; it declares
its independence family, whether it is deterministic, and a cost model. The registry is the planner's whole world."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

FAMILIES = ("sheet-reader", "record-text", "gazetteer", "address-register", "road-network", "basemap", "geometry")
KINDS = ("cue", "candidate", "hypothesis", "evidence")


@dataclass
class Tool:
    name: str
    consumes: tuple[str, ...]                  # object kinds it needs present in the state
    produces: str                              # one of KINDS
    family: str
    deterministic: bool
    cost_estimate: float                       # USD per call, upper bound
    run: Callable[["State"], list]             # (state) -> new objects of `produces`
    about: str = ""

    def __post_init__(self):
        if self.family not in FAMILIES:
            raise ValueError(f"family {self.family!r} not in {FAMILIES}")
        if self.produces not in KINDS or any(k not in KINDS for k in self.consumes):
            raise ValueError("consumes/produces must be object kinds")

    def summary(self) -> dict:
        return {"name": self.name, "consumes": list(self.consumes), "produces": self.produces, "family": self.family,
                "deterministic": self.deterministic, "cost_estimate": self.cost_estimate, "about": self.about}


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def add(self, t: Tool) -> "ToolRegistry":
        if t.name in self._tools:
            raise ValueError(f"tool {t.name!r} already registered")
        self._tools[t.name] = t
        return self

    def __getitem__(self, name: str) -> Tool:
        return self._tools[name]

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return list(self._tools)

    def summaries(self) -> list[dict]:
        return [t.summary() for t in self._tools.values()]

    def runnable(self, present: set[str]) -> list[str]:
        """Tools whose inputs are all present in the state."""
        return [n for n, t in self._tools.items() if set(t.consumes) <= present]
