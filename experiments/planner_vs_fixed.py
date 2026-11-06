#!/usr/bin/env python3
"""Experiment 1: the LLM planner against the fixed plan, same tools, same cache, same cases.

    python experiments/planner_vs_fixed.py --kind plans_gb --cases cases.jsonl --out DIR [--replay]

cases.jsonl: one JSON per line with the Sheet fields (id, image, record, meta) and a truth WKT + tolerance_m.
Writes per-case verdicts for both drivers, the planner's choices with its stated reasons, and the comparison:
planned sequence vs fixed sequence (same tools? order?), placed right / wrong / abstained for each, cost, and the
paired McNemar test. --replay answers every planner question from the local cache and refuses a live call."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.environ.get("GEO_EVAL_REPO", "/env/code/geo-eval")); sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evalcore import Calibrator, Policy, Rule, stats
from ga import Decider, FixedPlan, Planner, Sheet, kinds, run
from ga.bench import TruthCase, score
from ga.planner_llm import ClaudeCLIChooser, LLMChooser


def policy_for(kind: str) -> Policy:
    rules = []
    for r in kinds.KINDS[kind].policy_rules:
        expr = r["when"]
        rules.append(Rule(r["id"], (lambda f, e=expr: bool(eval(e, {}, {**{k: None for k in ("snap_iou", "address_inside", "address_in_footprint", "address_to_centre_m", "matchers_agree", "record_distance_m",
                                                                      "residual_within_bound", "editions_agree", "overlay_agreement", "n_candidates")}, **f}))),
                          r["to"], (r["from"],) if "from" in r else None, when_text=expr))
    return Policy(f"{kind}-rules", "v0", rules)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", required=True, choices=sorted(kinds.KINDS))
    ap.add_argument("--cases", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--replay", action="store_true")
    ap.add_argument("--max-cost", type=float, default=0.3)
    ap.add_argument("--chooser", choices=("deepseek", "claude-cli"), default="claude-cli")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    cases = [json.loads(l) for l in open(a.cases) if l.strip()]
    if a.replay:
        os.environ.pop("DEEPSEEK_API_KEY", None)
    chooser = (ClaudeCLIChooser if a.chooser == "claude-cli" else LLMChooser)(cache=out / "planner_cache.jsonl")
    reg = kinds.registry_for(a.kind)
    pol = policy_for(a.kind)
    dec = Decider(pol, None, lambda s: s.hypotheses[0].score if s.hypotheses else None)
    truth, verdicts = {}, {"fixed": {}, "planner": {}}
    seqs = {"fixed": {}, "planner": {}}
    for c in cases:
        sheet = Sheet(c["id"], kinds.KINDS[a.kind].kind, c["image"], c.get("digest", "sha256:" + c["id"]), c.get("record", {}), c.get("meta", {}))
        truth[c["id"]] = TruthCase(c["id"], c["truth_wkt"], c.get("crs", "EPSG:27700"), float(c.get("tolerance_m", 50)))
        for name, driver in (("fixed", FixedPlan(kinds.plan_for(a.kind))), ("planner", Planner(chooser, max_steps=12, max_cost=a.max_cost))):
            try:
                st = run(sheet, reg, driver, out / f"trace_{name}.jsonl")
                verdicts[name][c["id"]] = dec.decide(st)
                seqs[name][c["id"]] = [t["tool"] for t in st.trace if "skipped" not in t and t["tool"] != "planner"]
            except Exception as e:                                       # noqa: BLE001
                (out / "errors.log").open("a").write(f"{name} {c['id']}: {type(e).__name__}: {e}\n")
    s_fixed, s_plan = score(verdicts["fixed"], truth), score(verdicts["planner"], truth)
    right = {k: {r["case"]: r["outcome"] == "right" for r in s["rows"]} for k, s in (("fixed", s_fixed), ("planner", s_plan))}
    same_seq = sum(1 for cid in seqs["fixed"] if seqs["planner"].get(cid) == seqs["fixed"][cid])
    report = {"kind": a.kind, "n": len(cases), "fixed": {k: v for k, v in s_fixed.items() if k != "rows"},
              "planner": {k: v for k, v in s_plan.items() if k != "rows"},
              "paired": stats.paired({c: True for c in truth}, right["fixed"], right["planner"]),
              "planner_same_sequence_as_fixed": same_seq, "planner_calls": chooser.calls, "planner_cached": chooser.cached,
              "planner_choices": chooser.log}
    (out / "report.json").write_text(json.dumps(report, indent=1, default=str))
    (out / "rows.json").write_text(json.dumps({"fixed": s_fixed["rows"], "planner": s_plan["rows"], "sequences": seqs}, indent=1, default=str))
    print(json.dumps({k: report[k] for k in ("n", "paired", "planner_same_sequence_as_fixed", "planner_calls", "planner_cached")}, indent=1))
    print("fixed  :", {k: s_fixed[k] for k in ("placed", "placed_right", "placed_wrong", "abstained")})
    print("planner:", {k: s_plan[k] for k in ("placed", "placed_right", "placed_wrong", "abstained")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
