"""The primitive library: every operation a recipe may compose, declared once with its family, determinism and
contract. Generic primitives are implemented here; bound primitives wrap code from the two source projects and
import it lazily, so the library can be inspected (and recipes validated) on a machine that has neither."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from ..tools.registry import Tool


@dataclass
class Primitive:
    name: str
    family: str
    deterministic: bool
    consumes: tuple[str, ...]
    produces: str
    about: str
    impl: Optional[Callable] = None            # (state, **params) -> list of produced objects; None = declared only
    source: str = "generic"                    # "generic" | "plans_gb" | "soi" | "raster"
    cost_estimate: float = 0.0
    requires: tuple[str, ...] = ()             # external packages / repos the binding needs

    def available(self) -> bool:
        return self.impl is not None

    def tool(self, **params) -> Tool:
        if self.impl is None:
            raise RuntimeError(f"primitive {self.name!r} is declared but not implemented here")
        impl = self.impl
        return Tool(self.name, self.consumes, self.produces, self.family, self.deterministic, self.cost_estimate,
                    lambda state, _p=params: impl(state, **_p), self.about)


LIBRARY: dict[str, Primitive] = {}


def register(p: Primitive) -> Primitive:
    if p.name in LIBRARY:
        raise ValueError(f"primitive {p.name!r} already in the library")
    LIBRARY[p.name] = p
    return p


def names() -> set[str]:
    return set(LIBRARY)


def table() -> str:
    rows = ["| primitive | family | deterministic | consumes → produces | source | implemented |", "|---|---|---|---|---|---|"]
    for p in LIBRARY.values():
        rows.append(f"| {p.name} | {p.family} | {'yes' if p.deterministic else 'no'} | {', '.join(p.consumes) or '–'} → {p.produces} | {p.source} | {'yes' if p.available() else 'declared'} |")
    return "\n".join(rows)


from . import generic, plans_gb, soi, raster, claude_reader   # noqa: E402,F401  (registration on import)
