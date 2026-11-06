"""The main agent's first two moves for a batch of one to three similar sheets: profile them (a reading per sheet,
then what is common and what varies) and write the plan (knowledge retrieved for the profile, the library in view).
Execution, evaluation and the improvement loop then run the plan through the loop and geo-eval."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .claude_cli import ask_json
from .knowledge import Index
from .loop import State
from .model import Sheet
from .plan import Plan, make_plan
from .primitives import LIBRARY


def read_sheet(sheet: Sheet, reads_dir: str | None = None, headless: bool = True) -> dict:
    """Claude's reading of one sheet (cached file or headless), returned as the raw JSON the reader wrote."""
    from .primitives.claude_reader import claude_read
    st = State(sheet)
    claude_read(st, reads_dir=reads_dir, headless=headless)
    d = Path(reads_dir or "/data/lab/projects/georeference-anything/claude_reads") / f"{sheet.id}.json"
    return json.loads(d.read_text()) if d.exists() else {"cues": []}


def profile_batch(sheets: list[Sheet], readings: list[dict]) -> dict:
    """Common features across the batch and the per-sheet variation: cue kinds present, north arrow, scale, site marking."""
    per = []
    for s, r in zip(sheets, readings):
        kinds = Counter(c.get("kind") for c in r.get("cues", []))
        per.append({"sheet": s.id, "width": s.meta.get("width"), "height": s.meta.get("height"), "cue_kinds": dict(kinds),
                    "north_arrow": r.get("north_arrow"), "scale": r.get("scale"), "site_marking": r.get("site_marking"),
                    "note": r.get("note"), "record": dict(s.record)})
    common = set.intersection(*[set(p["cue_kinds"]) for p in per]) if per else set()
    union = set().union(*[set(p["cue_kinds"]) for p in per]) if per else set()
    return {"n_sheets": len(per), "kind_hint": sheets[0].kind if sheets else "", "cue_kinds_common": sorted(common),
            "cue_kinds_any": sorted(union), "variation": sorted(union - common), "sheets": per}


def plan_batch(sheets: list[Sheet], readings: list[dict], model: str = "claude-sonnet-5", cache: str | None = None, k: int = 6) -> tuple[Plan, dict, dict]:
    prof = profile_batch(sheets, readings)
    idx = Index()
    query = " ".join([prof["kind_hint"], " ".join(prof["cue_kinds_any"])] + [str(p.get("note") or "") for p in prof["sheets"]])
    kind = None if prof["kind_hint"] in ("", "unknown") else prof["kind_hint"]      # a blind batch: no kind filter on the knowledge
    knowledge = idx.context(query, kind=kind, cues=prof["cue_kinds_any"], k=k)
    plan, raw = make_plan(prof, knowledge, len(sheets), lambda system, user: ask_json(system, user, model=model, cache=cache))
    return plan, raw, {"profile": prof, "knowledge_ids": [c.id for _, c in idx.retrieve(query, kind, prof["cue_kinds_any"], k)]}
