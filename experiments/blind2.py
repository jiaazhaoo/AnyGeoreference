"""Blind test 2: unseen public maps, the whole flow. Per batch (1-3 similar sheets): read (Claude), profile, plan
(the main agent with the knowledge base), build what the plan says is missing (the builder), execute the recipe,
decide with the generic two-family policy, write the result. Nothing here knows the map; the record says only
what a stranger would say.

    python experiments/blind2.py --out /data/lab/.../blind2 --batch thames=/path/a.jpg --batch norwich1884=/p/l.jpg,/p/r.jpg
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0, "/env/code/geo-eval")
from PIL import Image                                                                        # noqa: E402

from ga import Sheet                                                                         # noqa: E402
from ga.builder import ensure_capabilities                                                    # noqa: E402
from ga.execute import execute_plan, summary                                                  # noqa: E402
from ga.model import digest_bytes                                                             # noqa: E402
from ga.orchestrate import plan_batch, read_sheet                                             # noqa: E402

Image.MAX_IMAGE_PIXELS = None


def sheet_of(path: str, record: dict) -> Sheet:
    with Image.open(path) as im:
        meta = {"width": im.width, "height": im.height}
    with open(path, "rb") as f:
        head = f.read(1 << 20)
    return Sheet(Path(path).stem, "unknown", path, digest_bytes(head), record, meta)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--batch", action="append", required=True, help="name=img1[,img2,...]")
    ap.add_argument("--record", default='{"note": "a scanned map, place and kind unknown to the system"}')
    ap.add_argument("--no-build", action="store_true")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    status = out / "status.txt"
    for b in a.batch:
        name, imgs = b.split("=", 1)
        t0 = time.time()
        rec = {"batch": name, "images": imgs.split(",")}
        try:
            sheets = [sheet_of(p, json.loads(a.record)) for p in imgs.split(",")]
            readings = [read_sheet(s, headless=True) for s in sheets]
            rec["readings"] = [{"sheet": s.id, "n_cues": len(r.get("cues", [])), "kinds": sorted({c.get("kind") for c in r.get("cues", [])}),
                                "north_arrow": r.get("north_arrow"), "scale": r.get("scale"), "note": r.get("note")} for s, r in zip(sheets, readings)]
            status.open("a").write(f"{name}: read {[x['n_cues'] for x in rec['readings']]} cues\n")
            plan, raw, ctx = plan_batch(sheets, readings, cache=str(out / f"{name}.plan.cache.jsonl"))
            rec["plan"] = plan.to_dict(); rec["knowledge_ids"] = ctx["knowledge_ids"]
            (out / f"{name}.plan.json").write_text(json.dumps({"plan": plan.to_dict(), "raw": raw, "context": ctx}, indent=1, default=str))
            status.open("a").write(f"{name}: plan {[s.primitive for s in plan.recipe.steps]} missing {[m.get('name') for m in plan.missing_primitives]}\n")
            if plan.missing_primitives and not a.no_build:
                rec["builds"] = ensure_capabilities(plan, None, log=out / "builds.jsonl")
                status.open("a").write(f"{name}: builds {[(x['name'], x['test_passed'], x['installed']) for x in rec['builds']]}\n")
            states, verdicts, skipped = execute_plan(plan, sheets, out / f"{name}.trace.jsonl")
            rec["skipped"] = skipped
            rec["results"] = [summary(st, v) for st, v in zip(states, verdicts)]
            status.open("a").write(f"{name}: " + "; ".join(f"{r['sheet']} {r['action']} ({r['why'][:60]})" for r in rec["results"]) + "\n")
        except Exception:                                                                    # noqa: BLE001
            rec["error"] = traceback.format_exc()[-2000:]
            status.open("a").write(f"{name}: ERROR {rec['error'].splitlines()[-1]}\n")
        rec["seconds"] = round(time.time() - t0)
        (out / f"{name}.result.json").write_text(json.dumps(rec, indent=1, default=str))
    status.open("a").write("ALL\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
