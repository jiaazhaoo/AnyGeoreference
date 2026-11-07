"""One evaluation for every suite, run against any version of the system (--repo): the plan-driven flow (read, plan,
optionally build, execute, revise) on blind/holdout batches, or a kind's fixed recipe on cases with truth. Each sheet's
best placement is scored against truth points: median distance between where the placement puts the truth points'
pixels and where they truly are. 'right' = within the case's tolerance. Accepted-wrong is the number that must not rise.

    python experiments/evaluate.py --repo /path/to/ga-version --suite holdout|blind|drawings10|soi6 --out DIR
"""
from __future__ import annotations

import argparse
import importlib
import json
import math
import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path("/data/lab/projects/georeference-anything")
RECORD = {"note": "a scanned map, place and kind unknown to the system"}


def batches(suite: str) -> list[dict]:
    if suite == "holdout":
        m = json.load(open(ROOT / "holdout-20261107/manifest.json"))
        return [{"name": x["id"], "sheets": [{"id": x["id"], "image": str(ROOT / "holdout-20261107" / x["image"]),
                 "truth": {"crs": "EPSG:4326", "points": [{"x": p["x"], "y": p["y"], "X": p["lon"], "Y": p["lat"]} for p in x["truth_points"]]},
                 "tolerance_m": max(100.0, 0.001 * x["scale"])}]} for x in m["maps"]]
    if suite == "blind":
        bt = json.load(open(ROOT / "regression/blind_truth.json"))
        usgs = json.load(open(ROOT / "regression/usgs1903_truth.json"))
        def t(sid):
            if sid not in bt:
                return None, None
            r = bt[sid]
            return {"crs": r["crs"], "points": r["truth_points"]}, max(250.0, 3 * r["residual_median_m"])
        def sh(sid, img):
            tr, tol = t(sid)
            return {"id": sid, "image": str(ROOT / img), "truth": tr, "tolerance_m": tol}
        return [
            {"name": "thames_chart_1900", "sheets": [sh("thames_chart_1900", "blind2/src/thames_chart_1900.jpg")]},
            {"name": "osd_norwich", "sheets": [sh("osd_norwich", "blind2/src/osd_norwich.jpg")]},
            {"name": "norwich_1884", "sheets": [sh("norwich_1884_left", "blind2/src/norwich_1884_left.jpg"), sh("norwich_1884_right", "blind2/src/norwich_1884_right.jpg")]},
            {"name": "leeds_1806", "sheets": [sh("leeds_1806", "blind2/src/leeds_1806.jpg")]},
            {"name": "sheffield_1823_plan", "sheets": [sh("sheffield_1823_plan", "blind/commons/Sheffield_1823_plan.jpg")]},
            {"name": "gleadless_valley_osm", "sheets": [sh("gleadless_valley_osm", "blind/commons/Gleadless_Valley_OSM.png")]},
            {"name": "cathedral_from_above", "sheets": [sh("cathedral_from_above", "blind/commons/Sheffield_-_the_cathedral_from_above_-_geograph.org.uk_-_1861401.jpg")]},
            {"name": "usgs_boston_bay_1903", "sheets": [{"id": "usgs_boston_bay_1903", "image": str(ROOT / "regression/usgs_boston_bay_1903.jpg"),
                                                         "truth": {"crs": "EPSG:4326", "points": usgs["points"]}, "tolerance_m": 100.0}]},
        ]
    raise ValueError(suite)


def error_m(h, truth) -> float | None:
    """Median metres between the placement's image of the truth pixels and the truth coordinates."""
    if h is None or not truth:
        return None
    from pyproj import Transformer
    a, b, c, d, e, f = h["transform"]
    tr = Transformer.from_crs(h["crs"], truth["crs"], always_xy=True)
    errs = []
    for p in truth["points"]:
        X, Y = a * p["x"] + b * p["y"] + c, d * p["x"] + e * p["y"] + f
        X, Y = tr.transform(X, Y)
        if truth["crs"].upper() == "EPSG:4326":
            k = 111320 * math.cos(math.radians(p["Y"]))
            errs.append(math.hypot((X - p["X"]) * k, (Y - p["Y"]) * 110574))
        else:
            errs.append(math.hypot(X - p["X"], Y - p["Y"]))
    errs.sort()
    return errs[len(errs) // 2] if all(map(math.isfinite, errs)) else None


def outcome(action, err, tol) -> str:
    if action == "accept":
        return "accepted_unverified" if err is None else ("accepted_right" if err <= tol else "accepted_WRONG")
    if action == "review":
        return "review_no_truth" if err is None else ("review_right" if err <= tol else "review_wrong")
    return "abstain"


def run_plan_suite(a, ga):
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    Sheet = ga["model"].Sheet; digest_bytes = ga["model"].digest_bytes
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True); rows = []
    for b in batches(a.suite):
        if a.only and b["name"] not in a.only.split(","):
            continue
        t0 = time.time(); rec = {"batch": b["name"]}
        try:
            sheets = []
            for s in b["sheets"]:
                with Image.open(s["image"]) as im:
                    meta = {"width": im.width, "height": im.height}
                sheets.append(Sheet(s["id"], "unknown", s["image"], digest_bytes(open(s["image"], "rb").read(1 << 20)), dict(RECORD), meta))
            readings = [ga["orchestrate"].read_sheet(s, headless=True) for s in sheets]
            plan, raw, ctx = ga["orchestrate"].plan_batch(sheets, readings, cache=str(out / f"{b['name']}.plan.cache.jsonl"))
            rec["plan"] = [s.primitive for s in plan.recipe.steps]; rec["missing"] = [m.get("name") for m in plan.missing_primitives]
            if plan.missing_primitives and a.build:
                rec["builds"] = ga["builder"].ensure_capabilities(plan, None, log=out / "builds.jsonl")
            states, verdicts, skipped = ga["execute"].execute_plan(plan, sheets, out / f"{b['name']}.trace.jsonl")
            for i in range(a.revisions):
                if any(v.action == "accept" for v in verdicts):
                    break
                summ = [ga["execute"].summary(st, v) for st, v in zip(states, verdicts)]
                new, rraw = ga["plan"].revise_plan(plan, summ, lambda s_, u_: ga["claude_cli"].ask_json(s_, u_, cache=str(out / f"{b['name']}.plan.cache.jsonl")))
                if new is None:
                    break
                plan = new
                states, verdicts, skipped = ga["execute"].execute_plan(plan, sheets, out / f"{b['name']}.trace.jsonl")
                rec.setdefault("revisions", []).append([s.primitive for s in plan.recipe.steps])
            for s, st, v in zip(b["sheets"], states, verdicts):
                h = st.hypotheses[0] if st.hypotheses else None
                hd = {"transform": list(h.transform), "crs": h.crs, "matcher": h.matcher, "score": h.score, "note": h.note[:200]} if h else None
                err = error_m(hd, s["truth"])
                rows.append({"batch": b["name"], "sheet": s["id"], "action": v.action, "why": v.why, "matcher": hd and hd["matcher"],
                             "error_m": None if err is None else round(err, 1), "tolerance_m": s["tolerance_m"], "outcome": outcome(v.action, err, s["tolerance_m"]),
                             "evidence": [(e.name, e.value if not isinstance(e.value, (list, dict)) else str(e.value)[:80], e.family) for e in st.evidence],
                             "hypothesis": hd, "steps": [(t["tool"], t.get("error") or t.get("skipped") or t.get("produced")) for t in st.trace]})
        except Exception:                                                                    # noqa: BLE001
            rec["error"] = traceback.format_exc()[-1500:]
            for s in b["sheets"]:
                rows.append({"batch": b["name"], "sheet": s["id"], "action": "error", "outcome": "error", "error": rec["error"].splitlines()[-1]})
        rec["seconds"] = round(time.time() - t0)
        with open(out / "batches.jsonl", "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        print(b["name"], [(r["sheet"], r["outcome"], r.get("error_m")) for r in rows if r["batch"] == b["name"]], flush=True)
    return rows


def run_kind_suite(a, ga):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from planner_vs_fixed import policy_for
    kinds, loop, decide = ga["kinds"], ga["loop"], ga["decide"]
    Sheet = ga["model"].Sheet
    kind = {"drawings10": "plans_gb", "soi6": "soi_1inch"}[a.suite]
    cases = [json.loads(l) for l in open(ROOT / ("cases_drawings10.jsonl" if a.suite == "drawings10" else "regression/cases_soi6.jsonl")) if l.strip()]
    reg = kinds.registry_for(kind); dec = decide.Decider(policy_for(kind), None, lambda s: s.hypotheses[0].score if s.hypotheses else None)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True); rows = []
    import shapely.wkt
    from pyproj import Transformer
    for c in cases:
        sheet = Sheet(c["id"], kinds.KINDS[kind].kind, c["image"], c.get("digest", "sha256:" + c["id"]), c.get("record", {}), c.get("meta", {}))
        try:
            st = loop.run(sheet, reg, loop.FixedPlan(kinds.plan_for(kind)), out / "trace.jsonl"); v = dec.decide(st)
            h = st.hypotheses[0] if st.hypotheses else None
            err = None
            if h is not None:
                g, tg = shapely.wkt.loads(h.site_wkt).centroid, shapely.wkt.loads(c["truth_wkt"]).centroid
                tr = Transformer.from_crs(h.crs, c.get("crs", "EPSG:27700"), always_xy=True); X, Y = tr.transform(g.x, g.y)
                if c.get("crs", "EPSG:27700").upper() == "EPSG:4326":
                    err = math.hypot((X - tg.x) * 111320 * math.cos(math.radians(tg.y)), (Y - tg.y) * 110574)
                else:
                    err = math.hypot(X - tg.x, Y - tg.y)
            tol = float(c.get("tolerance_m", 50))
            rows.append({"sheet": c["id"], "action": v.action, "why": v.why, "matcher": h and h.matcher, "error_m": None if err is None else round(err, 1),
                         "tolerance_m": tol, "outcome": outcome(v.action, err, tol),
                         "evidence": [(e.name, e.value if not isinstance(e.value, (list, dict)) else str(e.value)[:80], e.family) for e in st.evidence]})
        except Exception:                                                                    # noqa: BLE001
            rows.append({"sheet": c["id"], "action": "error", "outcome": "error", "error": traceback.format_exc().splitlines()[-1]})
        print(rows[-1]["sheet"], rows[-1]["outcome"], rows[-1].get("error_m"), flush=True)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True); ap.add_argument("--suite", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--revisions", type=int, default=2); ap.add_argument("--build", action="store_true"); ap.add_argument("--only", default="")
    a = ap.parse_args()
    sys.path.insert(0, "/env/code/geo-eval"); sys.path.insert(0, a.repo)
    ga = {m: importlib.import_module(f"ga.{m}") for m in ("model", "orchestrate", "execute", "plan", "claude_cli", "builder", "kinds", "loop", "decide")}
    print("ga from", ga["model"].__file__, flush=True)
    rows = run_plan_suite(a, ga) if a.suite in ("holdout", "blind") else run_kind_suite(a, ga)
    from collections import Counter
    summary = {"suite": a.suite, "repo": a.repo, "n": len(rows), "outcomes": dict(Counter(r["outcome"] for r in rows)),
               "placed_within_tolerance": sum(1 for r in rows if r.get("error_m") is not None and r["error_m"] <= (r.get("tolerance_m") or 0))}
    Path(a.out, "rows.json").write_text(json.dumps(rows, indent=1, default=str))
    Path(a.out, "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
