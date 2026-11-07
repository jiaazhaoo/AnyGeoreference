"""A vision-language reader fulfilled by Claude. Two ways to fulfil it:
  - offline: Claude read the sheet in a conversation and wrote the cues to <claude_reads_dir>/<sheet id>.json
    ({"cues": [{"kind", "text", "bbox": [x0, y0, x1, y1], "confidence"}], "north_arrow", "scale", "site_marking", "note"})
  - headless: `claude -p` with the image (the platform's own subscription); same JSON contract, cached to the same file
The loop treats both the same: cues with pixel boxes, family sheet-reader, source model."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from ..model import Cue
from . import Primitive, register

PROMPT = """Read this scanned map or drawing. Return one JSON object only:
{"cues": [{"kind": "road|number|place|landmark|arrow|scale|grid|text", "text": "...", "bbox": [x0, y0, x1, y1], "confidence": 0..1}],
 "north_arrow": "up|rotated N deg|none", "scale": "1:500|none", "site_marking": "red line|hatched|none|...", "note": "one sentence"}
bbox in image pixels (the image is {w} x {h}). Road names and house numbers matter most: list EVERY street or road name you can read, up to 80, each with its own bbox; then places, landmarks, numbers. For survey sheets and charts also give the printed corner coordinates or border scale values as grid cues with their exact text (e.g. "51 30' N" at the left border); read all four corners and the edges. The title usually names the place ("PLAN of the TOWN of X", "X Quadrangle", "X to Y"): give each place it names as a place cue as well. Never give coordinates on the Earth.
"text" is the label exactly as printed (e.g. "Briggate"), never a description or a comment; put remarks in "note". Skip anything you cannot actually read.
You have only the Read tool: read the image file once as it is; do not try to crop, zoom, or run code, and do not ask for other tools."""


READS = int(os.environ.get("GA_READS", "2"))      # independent readings per sheet (knowledge: reading-hallucination-guard)


def _norm(t: str) -> str:
    return "".join(ch for ch in str(t).lower() if ch.isalnum())


def _read_once(state, f: Path, model: str, n: int) -> None:
    from ..claude_cli import ask_json
    w, h = state.sheet.meta.get("width", 0), state.sheet.meta.get("height", 0)
    tail = f"\nRead the image file at this path with your Read tool: {state.sheet.image}"
    if n > 1:
        tail += f"\n(Independent reading no. {n}: read the whole sheet again from scratch, edges and margins included.)"
    data = ask_json("You read scanned maps and drawings for a georeferencing system.",
                    PROMPT.replace("{w}", str(w)).replace("{h}", str(h)) + tail,
                    model=model, max_turns=8, allowed_tools="Read", timeout=600)
    data["reader"] = f"claude headless ({model}), reading {n}"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, indent=1))


def merged_reading(sheet_id: str, d: Path) -> dict:
    """All readings of a sheet merged: the union of cues (one per text), each marked confirmed when every reading
    found it; header fields from the first reading that has them. A cue only one reading saw is kept (a missed border
    figure is the commoner failure than an invented one) with its confidence capped, so matchers can rank it lower."""
    files = [d / f"{sheet_id}.json"] + sorted(d.glob(f"{sheet_id}.r[0-9]*.json"))
    reads = [json.loads(x.read_text()) for x in files if x.exists()]
    if not reads:
        return {"cues": []}
    if len(reads) == 1:
        return reads[0]
    seen: dict[str, dict] = {}
    counts: dict[str, int] = {}
    for r in reads:
        for c in r.get("cues", []):
            k = _norm(c.get("text", ""))
            if not k:
                continue
            counts[k] = counts.get(k, 0) + 1
            seen.setdefault(k, dict(c))
    cues = []
    for k, c in seen.items():
        c = dict(c)
        c["confirmed"] = counts[k] >= len(reads)
        if not c["confirmed"]:
            c["confidence"] = min(float(c.get("confidence", 0.8)), 0.5)
        cues.append(c)
    out = {key: next((r.get(key) for r in reads if r.get(key) not in (None, "", "none")), reads[0].get(key)) for key in ("north_arrow", "scale", "site_marking", "note")}
    out["cues"] = cues
    out["n_readings"] = len(reads)
    out["confirmed_share"] = round(sum(c["confirmed"] for c in cues) / max(1, len(cues)), 3)
    return out


def claude_read(state, reads_dir: str | None = None, headless: bool = False, model: str = "claude-sonnet-5", reads: int | None = None):
    d = Path(reads_dir or state.sheet.meta.get("claude_reads_dir") or os.environ.get("GA_CLAUDE_READS", "/data/lab/projects/georeference-anything/claude_reads"))
    n = READS if reads is None else reads
    for i in range(1, max(1, n) + 1):
        f = d / (f"{state.sheet.id}.json" if i == 1 else f"{state.sheet.id}.r{i}.json")
        if not f.exists() and headless:
            _read_once(state, f, model, i)
    data = merged_reading(state.sheet.id, d)
    out = []
    for c in data.get("cues", []):
        kind = c.get("kind", "text")
        if kind not in ("road", "number", "place", "landmark", "arrow", "scale", "grid", "text"):
            kind = "text"
        try:
            out.append(Cue(state.sheet.digest, kind, str(c["text"]).strip(), tuple(float(v) for v in c["bbox"]), "claude_read", float(c.get("confidence", 0.8))))
        except (KeyError, TypeError, ValueError):
            continue
    if data.get("n_readings", 1) > 1:
        from evalcore import Evidence
        state.evidence.append(Evidence("reader_agreement", data["confirmed_share"], "model", "sheet-reader", note=f"{data['n_readings']} readings"))
    return out


register(Primitive("claude_read", "sheet-reader", False, (), "cue",
                   "Claude reads the sheet: road names, numbers, places, north arrow, scale, site marking (offline file or headless CLI)",
                   claude_read, "generic", cost_estimate=0.0, requires=("claude CLI login, or a reads file",)))
