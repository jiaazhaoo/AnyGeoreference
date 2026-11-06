"""Level 2 objects: Profile -> Recipe -> AdapterSpec -> Pilot -> RecipeVersion. Data, not code: the adapter is
rendered from the spec, and the spec may only compose declared primitives."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence


def _digest(obj: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


@dataclass(frozen=True)
class Profile:
    """Measured on sample sheets. Every field is an observation with a method, never a guess."""
    kind_hint: str                                   # user's words for the kind, e.g. "1-inch survey sheet 1917"
    samples: tuple[str, ...]                         # sheet digests profiled
    colour_plates: tuple[str, ...] = ()              # e.g. ("black", "brown", "blue", "green")
    text_kinds: tuple[str, ...] = ()                 # e.g. ("place", "road", "number", "elevation", "gothic")
    scripts: tuple[str, ...] = ("latin",)
    printed_grid: str = "none"                       # "none" | "graticule" | "national-grid" | "corner-coordinates"
    scale_hint: str = ""                             # "1:63360", "1:1250", ""
    projection_hint: str = ""
    symbols: tuple[str, ...] = ()
    era: str = ""
    measured_by: Mapping[str, str] = field(default_factory=dict)   # field -> method that measured it


@dataclass(frozen=True)
class Step:
    primitive: str                                   # name in the primitive library
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Recipe:
    name: str
    kind: str
    profile: Profile
    cues: tuple[str, ...]                            # cue kinds to read
    references: tuple[str, ...]                      # families to query: gazetteer, address-register, ...
    matchers: tuple[str, ...]
    verifications: tuple[str, ...]
    policy_rules: tuple[Mapping[str, Any], ...]      # rule rows for evalcore.Policy
    expected_accuracy_m: tuple[float, float] = (0.0, 0.0)   # band
    expected_cost_per_sheet: float = 0.0
    derived_from: str = ""                           # a frozen RecipeVersion digest, or ""
    note: str = ""


@dataclass(frozen=True)
class AdapterSpec:
    """The adapter as data: an ordered composition of primitives. Code is rendered from this."""
    recipe: str                                      # Recipe digest
    steps: tuple[Step, ...]
    policy: tuple[Mapping[str, Any], ...]
    library_version: str                             # which primitive library the names resolve against

    def validate(self, library: set[str]) -> list[str]:
        """Composition-only: every step must name a primitive in the library."""
        return [s.primitive for s in self.steps if s.primitive not in library]


@dataclass(frozen=True)
class Pilot:
    sheets: tuple[str, ...]                          # digests
    truth_source: str                                # "control-points" | "known-locations" | "cross-edition" | "archive-published"
    metrics: Mapping[str, Any]                       # placed_right, placed_wrong, abstained, cost, calibration
    gate_ok: bool
    gate_log: str = ""


@dataclass(frozen=True)
class RecipeVersion:
    recipe: Recipe
    spec: AdapterSpec
    pilot: Pilot
    version: str

    def __post_init__(self):
        if not self.pilot.gate_ok:
            raise ValueError("a recipe is frozen only after its pilot passed the gate")

    def digest(self) -> str:
        return _digest({"recipe": asdict(self.recipe), "spec": asdict(self.spec), "pilot": asdict(self.pilot), "version": self.version})
