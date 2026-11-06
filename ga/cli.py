"""ga: run one sheet, list kinds and primitives.

    python -m ga.cli kinds
    python -m ga.cli primitives
    python -m ga.cli run --kind soi_1inch --image sheet.tif --record '{"sheet_code": "053BSW"}' [--planner] [--trace out.jsonl]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.environ.get("GEO_EVAL_REPO", "/env/code/geo-eval"))


def main(argv=None) -> int:
    from . import kinds
    from .loop import FixedPlan, Planner, run
    from .model import Sheet, digest_bytes
    from .primitives import LIBRARY, table
    ap = argparse.ArgumentParser(prog="ga")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("kinds"); sub.add_parser("primitives")
    r = sub.add_parser("run")
    r.add_argument("--kind", required=True, choices=sorted(kinds.KINDS))
    r.add_argument("--image", required=True)
    r.add_argument("--record", default="{}", help="JSON: address, sheet_code, hint_xy ...")
    r.add_argument("--meta", default="{}", help="JSON: width, height, town_xy, ocr_jsonl, page, cpu_only ...")
    r.add_argument("--planner", action="store_true", help="let an LLM choose the tools (DEEPSEEK_BASE_URL / DEEPSEEK_API_KEY)")
    r.add_argument("--max-cost", type=float, default=0.5)
    r.add_argument("--trace", help="append the trace to this JSONL")
    a = ap.parse_args(argv)
    if a.cmd == "kinds":
        for k, rec in kinds.KINDS.items():
            miss = kinds.unavailable(k)
            print(f"{k:<20} {rec.kind:<18} steps {len(kinds.SPECS[k].steps):2d}  cues {','.join(rec.cues) or '-'}  "
                  f"unavailable here: {','.join(miss) or 'none'}")
        return 0
    if a.cmd == "primitives":
        print(table()); return 0
    record, meta = json.loads(a.record), json.loads(a.meta)
    if "width" not in meta or "height" not in meta:
        try:
            from PIL import Image
            Image.MAX_IMAGE_PIXELS = None
            with Image.open(a.image) as im:
                meta.setdefault("width", im.width); meta.setdefault("height", im.height)
        except Exception:                                                   # noqa: BLE001
            pass
    with open(a.image, "rb") as f:
        head = f.read(1 << 20)
    sheet = Sheet(Path(a.image).stem, kinds.KINDS[a.kind].kind, a.image, digest_bytes(head), record, meta)
    reg = kinds.registry_for(a.kind)
    if a.planner:
        from .planner_llm import LLMChooser
        driver = Planner(LLMChooser(cache=os.environ.get("GA_PLANNER_CACHE")), max_cost=a.max_cost)
    else:
        driver = FixedPlan(kinds.plan_for(a.kind))
    st = run(sheet, reg, driver, a.trace)
    print(json.dumps({"sheet": sheet.id, "kind": a.kind, "driver": type(driver).__name__,
                      "steps": [(t["tool"], t.get("produced", t.get("skipped", t.get("chose")))) for t in st.trace],
                      "cues": len(st.cues), "candidates": len(st.candidates),
                      "hypotheses": [{"matcher": h.matcher, "score": round(h.score, 3), "note": h.note[:100]} for h in st.hypotheses[:3]],
                      "evidence": [{"name": e.name, "value": e.value, "family": e.family} for e in st.evidence],
                      "cost": round(st.cost, 4), "seconds": round(st.seconds, 2)}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
