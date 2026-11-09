"""Run a kind's fixed recipe on a coordinate-free benchmark and score it.

    python benchmarks/run_coordfree.py benchmarks/coordfree_dev_usgs.json --kind street_map --out benchmarks/results/coordfree_dev_usgs_street_map

Each window is one sheet; its three hint tiers are three runs of that sheet with a different record. The record holds
only the hint (or nothing). Readings are cached per window, so the tiers share one reading. The system sees the
window image and the record; the truth files are opened by the scorer only, after every run.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "benchmarks"))

import coordfree as cf                                             # noqa: E402
from ga import Decider, FixedPlan, Sheet, kinds, run              # noqa: E402
from ga.model import digest_bytes                                  # noqa: E402


def sheet_for(cid: str, image: Path, hint: str, reads: Path, kind: str) -> Sheet:
    from PIL import Image
    with Image.open(image) as im:
        w, h = im.size
    with open(image, "rb") as f:
        dig = digest_bytes(f.read(1 << 20))
    record = {"note": hint or "a map extract; place unknown", "hint": hint}
    return Sheet(cid, kind, str(image), dig, record, {"width": w, "height": h, "claude_reads_dir": str(reads)})


def pairs_of(hyp, w: int, h: int) -> list:
    """The placement as control pairs [x, y, lon, lat] on a 3 x 3 grid over the window."""
    from pyproj import Transformer
    a, b, c, d, e, f = hyp.transform
    xs, ys = np.meshgrid(np.linspace(0, w, 3), np.linspace(0, h, 3))
    px = np.c_[xs.ravel(), ys.ravel()]
    X, Y = a * px[:, 0] + b * px[:, 1] + c, d * px[:, 0] + e * px[:, 1] + f
    lon, lat = Transformer.from_crs(hyp.crs, "EPSG:4326", always_xy=True).transform(X, Y)
    return [[float(p[0]), float(p[1]), float(lo), float(la)] for p, lo, la in zip(px, lon, lat)]


def run_one(item, kind: str, reads: Path) -> tuple:
    cid, tier, image, hint = item
    sh = sheet_for(cid, image, hint, reads, kind)
    st = run(sh, kinds.registry_for(kind), FixedPlan(kinds.plan_for(kind)))
    v = Decider(kinds.policy_for(kind), None, lambda s: s.hypotheses[0].score if s.hypotheses else None).decide(st)
    cues = Counter(c.kind for c in st.cues)
    errors = [f"{t['tool']}: {t['error']}" for t in st.trace if t.get("error")]
    ans = {"action": "abstain" if v.action not in ("accept", "review") else v.action, "why": v.why,
           "cues": dict(cues), "candidates": len(st.candidates), "hypotheses": len(st.hypotheses), "errors": errors}
    if ans["action"] != "abstain" and st.hypotheses:
        ans["pairs"] = pairs_of(st.hypotheses[0], sh.meta["width"], sh.meta["height"])
    return cid, tier, ans


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cases")
    ap.add_argument("--kind", default="street_map")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    data = ROOT / "benchmarks" / "data" / "coordfree" / Path(a.cases).stem
    reads = data / "reads"
    items = list(cf.inputs(a.cases, data))
    # read every window once first (the tiers share it), then run the tiers
    first = [it for it in items if it[1] == "none"]
    rest = [it for it in items if it[1] != "none"]
    results: dict = {}
    with ThreadPoolExecutor(a.workers) as ex:
        for batch in (first, rest):
            for cid, tier, ans in ex.map(lambda it: run_one(it, a.kind, reads), batch):
                results.setdefault(cid, {})[tier] = ans
                print(f"  {cid} {tier}: {ans['action']} {ans['why'][:80]} cues={ans['cues']}", flush=True)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    score = cf.score(a.cases, results, data)
    for r in score["rows"]:
        ans = results[r["id"]][r["tier"]]
        r.update(cues=ans["cues"], errors=ans["errors"])
    out.with_suffix(".json").write_text(json.dumps({"cases": a.cases, "kind": a.kind, "tally": score["tally"],
                                                    "rows": score["rows"]}, indent=1))
    print(json.dumps(score["tally"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
