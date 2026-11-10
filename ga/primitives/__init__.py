"""The primitive library: every operation a recipe may compose, declared once with its family, determinism and
contract. Generic primitives are implemented here; bound primitives wrap code from the two source projects and
import it lazily, so the library can be inspected (and recipes validated) on a machine that has neither."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from ..tools.registry import Tool


def coerce_params(impl, params: dict) -> tuple[dict, list[str]]:
    """Planner params cast to the type of the primitive's default (a number given as "300" becomes 300.0; a range
    string "0.02-5" for a float is dropped and the default stands). Returns (kept, dropped-with-reason)."""
    import inspect
    sig = inspect.signature(impl).parameters
    kept, dropped = {}, []
    import os
    for k, v in params.items():
        if k in ("db", "gpkg", "path") or k.endswith("_path") or k.endswith("_dir"):     # data locations belong to the library, not the plan
            if not (isinstance(v, str) and os.path.isabs(v) and os.path.exists(v)):
                dropped.append(f"{k}={v!r} (not an existing absolute path; the library default stands)"); continue
        d = sig[k].default if k in sig else inspect.Parameter.empty
        if d is inspect.Parameter.empty or d is None or v is None:
            kept[k] = v; continue
        try:
            if isinstance(d, bool):
                kept[k] = v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes")
            elif isinstance(d, (int, float)):
                kept[k] = type(d)(float(v)) if isinstance(d, int) else float(v)
            elif isinstance(d, tuple):
                kept[k] = tuple(v) if isinstance(v, (list, tuple)) else (v,)
            elif isinstance(d, str):
                kept[k] = str(v)
            else:
                kept[k] = v
        except (TypeError, ValueError):
            dropped.append(f"{k}={v!r} (wants {type(d).__name__})")
    return kept, dropped


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
    uses: tuple[str, ...] = ()                 # reference families a matcher's fit consumes (independence of checks)
    sheet_params: tuple[str, ...] = ()         # numeric params that are facts read off the sheet (a plan may set them)

    def available(self) -> bool:
        return self.impl is not None

    def accepted_params(self) -> set[str]:
        import inspect
        if self.impl is None:
            return set()
        return {k for k in inspect.signature(self.impl).parameters if k != "state"}

    def plan_params(self, params: dict) -> tuple[dict, list[str]]:
        """What an agent's plan may set: facts the sheet supplies (required params, params named in `sheet_params`)
        and choices of method or data subset (non-numeric params). Numeric thresholds with a default are owned by the
        library: they were measured on benchmarks, and a plan that tunes them to get one sheet through is fitting a
        case, not using a capability."""
        import inspect
        if self.impl is None:
            return dict(params), []
        sig = inspect.signature(self.impl).parameters
        kept, dropped = {}, []
        for k, v in params.items():
            d = sig[k].default if k in sig else inspect.Parameter.empty
            numeric_default = isinstance(d, (int, float)) and not isinstance(d, bool)
            if numeric_default and k not in self.sheet_params:
                dropped.append(f"{k}={v!r} (threshold owned by the library)")
            else:
                kept[k] = v
        return kept, dropped

    def unknown_params(self, params: dict) -> list[str]:
        bad = coerce_params(self.impl, {k: v for k, v in params.items() if k in self.accepted_params()})[1] if self.impl else []
        return [k for k in params if k not in self.accepted_params()] + bad

    def tool(self, **params) -> Tool:
        if self.impl is None:
            raise RuntimeError(f"primitive {self.name!r} is declared but not implemented here")
        import inspect
        impl = self.impl
        known = coerce_params(impl, {k: v for k, v in params.items() if k in self.accepted_params()})[0]    # unknown names and wrong types dropped
        required = [k for k, v in inspect.signature(impl).parameters.items() if k != "state" and v.default is inspect.Parameter.empty
                    and v.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)]
        missing = [k for k in required if k not in known]
        if missing:                                                               # the plan did not give what the primitive needs: a fact, not a crash
            def _skip(state, _m=tuple(missing), _n=self.name):
                from evalcore import Evidence
                state.evidence.append(Evidence(f"{_n}_missing_params", list(_m), "deterministic", self.family, note="the plan gave no value for these required params"))
                return []
            return Tool(self.name, self.consumes, self.produces, self.family, self.deterministic, self.cost_estimate, _skip, self.about + " (missing params)")
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


from . import generic, graticule, basemap, plans_gb, soi, raster, claude_reader, names_world   # noqa: E402,F401  (registration on import)


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
