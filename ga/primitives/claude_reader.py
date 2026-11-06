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
bbox in image pixels (the image is {w} x {h}). Road names and house numbers matter most. Never give coordinates on the Earth."""


def claude_read(state, reads_dir: str | None = None, headless: bool = False, model: str = "claude-sonnet-5"):
    d = Path(reads_dir or state.sheet.meta.get("claude_reads_dir") or os.environ.get("GA_CLAUDE_READS", "/data/lab/projects/georeference-anything/claude_reads"))
    f = d / f"{state.sheet.id}.json"
    if not f.exists() and headless:
        from ..claude_cli import ask_json
        w, h = state.sheet.meta.get("width", 0), state.sheet.meta.get("height", 0)
        data = ask_json("You read scanned maps and drawings for a georeferencing system.",
                        PROMPT.replace("{w}", str(w)).replace("{h}", str(h)) + f"\nRead the image file at this path with your Read tool: {state.sheet.image}",
                        model=model, max_turns=3, allowed_tools="Read", timeout=400)
        d.mkdir(parents=True, exist_ok=True)
        data["reader"] = f"claude headless ({model})"
        f.write_text(json.dumps(data, indent=1))
    if not f.exists():
        return []
    data = json.loads(f.read_text())
    out = []
    for c in data.get("cues", []):
        kind = c.get("kind", "text")
        if kind not in ("road", "number", "place", "landmark", "arrow", "scale", "grid", "text"):
            kind = "text"
        out.append(Cue(state.sheet.digest, kind, str(c["text"]).strip(), tuple(float(v) for v in c["bbox"]), "claude_read", float(c.get("confidence", 0.8))))
    return out


register(Primitive("claude_read", "sheet-reader", False, (), "cue",
                   "Claude reads the sheet: road names, numbers, places, north arrow, scale, site marking (offline file or headless CLI)",
                   claude_read, "generic", cost_estimate=0.0, requires=("claude CLI login, or a reads file",)))
