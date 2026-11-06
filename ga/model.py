"""The objects of the loop. Invariants are checked at construction: a Cue has no coordinates, a Hypothesis has no
reader, a Verdict has a probability or is an abstention. Every object carries the digest of its sheet."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

ABSTAIN = "abstain"
CUE_KINDS = ("road", "number", "place", "landmark", "arrow", "scale", "grid", "text")
CANDIDATE_SOURCES = ("gazetteer", "address-register", "road-network", "basemap", "record-text")


def digest_bytes(b: bytes) -> str:
    return "sha256:" + hashlib.sha256(b).hexdigest()


@dataclass(frozen=True)
class Sheet:
    id: str
    kind: str                                  # adapter key: "plans_gb", "microfilm", "historical_map"
    image: str                                 # path or URI; the adapter knows how to open it
    digest: str                                # content digest of the image
    record: Mapping[str, str] = field(default_factory=dict)   # text that came with the sheet: address, description
    meta: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Cue:
    """Something read off the sheet. Where it is ON THE SHEET (pixels), never where it is on the Earth."""
    sheet: str                                 # Sheet.digest
    kind: str
    text: str
    bbox: tuple[float, float, float, float]    # x0, y0, x1, y1 in sheet pixels
    reader: str                                # tool name that produced it
    confidence: float = 1.0

    def __post_init__(self):
        if self.kind not in CUE_KINDS:
            raise ValueError(f"cue kind {self.kind!r} not in {CUE_KINDS}")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("cue confidence must be in [0, 1]")


@dataclass(frozen=True)
class Candidate:
    """An area on the Earth that could hold some cues. Produced by retrieval, never by a reader."""
    sheet: str
    source: str
    area_wkt: str                              # polygon in the target CRS
    crs: str
    answers: tuple[str, ...]                   # cue texts it answers
    score: float = 0.0
    note: str = ""

    def __post_init__(self):
        if self.source not in CANDIDATE_SOURCES:
            raise ValueError(f"candidate source {self.source!r} not in {CANDIDATE_SOURCES}")


@dataclass(frozen=True)
class Hypothesis:
    """A placement: a transform from sheet pixels to the CRS, the site polygon in the CRS, a score. Deterministic."""
    sheet: str
    transform: tuple[float, ...]               # 6 affine coefficients (a, b, c, d, e, f): x' = a x + b y + c ...
    site_wkt: str
    crs: str
    score: float
    matcher: str
    candidates: tuple[int, ...] = ()           # indices into the state's candidate list
    note: str = ""

    def __post_init__(self):
        if len(self.transform) != 6:
            raise ValueError("transform must have 6 affine coefficients")


@dataclass(frozen=True)
class Verdict:
    sheet: str
    placement: Hypothesis | None               # None = abstain
    probability: float | None
    action: str                                # "accept" | "review" | ABSTAIN
    why: str
    trail: tuple[str, ...]
    cost: float
    seconds: float

    def __post_init__(self):
        if self.placement is not None and self.probability is None:
            raise ValueError("a placement needs a calibrated probability")
        if self.placement is None and self.action != ABSTAIN:
            raise ValueError("no placement means the action is abstain")
