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

    def accepted_params(self) -> set[str]:
        import inspect
        if self.impl is None:
            return set()
        return {k for k in inspect.signature(self.impl).parameters if k != "state"}

    def unknown_params(self, params: dict) -> list[str]:
        return [k for k in params if k not in self.accepted_params()]

    def tool(self, **params) -> Tool:
        if self.impl is None:
            raise RuntimeError(f"primitive {self.name!r} is declared but not implemented here")
        impl = self.impl
        known = {k: v for k, v in params.items() if k in self.accepted_params()}    # a planner may name params the primitive has not got
        return Tool(self.name, self.consumes, self.produces, self.family, self.deterministic, self.cost_estimate,
                    lambda state, _p=known: impl(state, **_p), self.about)


LIBRARY: dict[str, Primitive] = {}


import os as _os
HIDDEN = {n for n in _os.environ.get("GA_HIDE_PRIMITIVES", "").split(",") if n}     # a demo: pretend these are absent


def register(p: Primitive) -> Primitive:
    if p.name in HIDDEN:
        return p
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


def load_generated() -> list[str]:
    """Import every module under ga/primitives/generated (built by the builder); returns the names loaded."""
    import importlib, pkgutil
    from . import generated
    out = []
    for m in pkgutil.iter_modules(generated.__path__):
        importlib.import_module(f"{__name__}.generated.{m.name}")
        out.append(m.name)
    return out


load_generated()
