"""Benchmark and metrics for a kind: verdicts against known locations, through geo-eval's Benchmark and Gate.

Truth per case: a polygon (WKT, in the kind's CRS) whose location is confirmed externally, and a tolerance in metres.
A verdict is *placed right* when the hypothesis footprint's centre lies within tolerance of the truth's centre (or the
footprints overlap at IoU >= iou_min when both are site polygons), *placed wrong* when it placed but failed that,
*abstained* when it did not place. For the gate: label 'right' = the truth exists; action 'accept' = placed; so a
placed-wrong case is a missed error only if its label is 'wrong' -- here every truth case is 'right', and the number
that must not rise is `placed_wrong` (reported as such), with abstentions as the review load."""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from evalcore import stats
from .model import Verdict, ABSTAIN


@dataclass(frozen=True)
class TruthCase:
    case: str
    wkt: str
    crs: str
    tolerance_m: float
    source: str = ""


def read_truth(path: str | Path) -> dict[str, TruthCase]:
    out = {}
    with open(path) as f:
        for r in csv.DictReader(f):
            out[r["case"]] = TruthCase(r["case"], r["wkt"], r.get("crs", "EPSG:27700"), float(r.get("tolerance_m", 50)), r.get("source", ""))
    return out


def _centre_dist_m(wkt_a: str, wkt_b: str, crs: str) -> float | None:
    import shapely.wkt
    a, b = shapely.wkt.loads(wkt_a), shapely.wkt.loads(wkt_b)
    if a.is_empty or b.is_empty:
        return None
    ca, cb = a.centroid, b.centroid
    if crs.upper() in ("EPSG:4326", "WGS84"):
        lat0 = (ca.y + cb.y) / 2
        return math.hypot((ca.x - cb.x) * 111320 * math.cos(math.radians(lat0)), (ca.y - cb.y) * 110574)
    return float(ca.distance(cb))


def score(verdicts: Mapping[str, Verdict], truth: Mapping[str, TruthCase]) -> dict:
    """Per case: right / wrong / abstain, with distances; totals with Wilson intervals; cost and seconds."""
    rows, n_right = [], 0
    for c, t in truth.items():
        v = verdicts.get(c)
        if v is None or v.placement is None:
            rows.append({"case": c, "outcome": "abstain", "dist_m": None, "p": None, "cost": v.cost if v else 0.0})
            continue
        d = _centre_dist_m(v.placement.site_wkt, t.wkt, t.crs)
        ok = d is not None and d <= t.tolerance_m
        if v.action != "accept":                                  # a hypothesis sent to a person is not a placement acted on
            rows.append({"case": c, "outcome": "review", "would_be": "right" if ok else "wrong", "dist_m": d, "p": v.probability, "cost": v.cost})
            continue
        rows.append({"case": c, "outcome": "right" if ok else "wrong", "dist_m": d, "p": v.probability, "cost": v.cost})
    n = len(rows)
    placed = [r for r in rows if r["outcome"] in ("right", "wrong")]
    reviewed = [r for r in rows if r["outcome"] == "review"]
    right = [r for r in placed if r["outcome"] == "right"]
    wrong = [r for r in placed if r["outcome"] == "wrong"]
    probs = [r["p"] for r in placed if r["p"] is not None]; outs = [r["outcome"] == "right" for r in placed if r["p"] is not None]
    return {"n": n, "placed": len(placed), "placed_right": stats.rate(len(right), n), "placed_wrong": stats.rate(len(wrong), n),
            "reviewed": stats.rate(len(reviewed), n), "reviewed_would_be_wrong": sum(1 for r in reviewed if r.get("would_be") == "wrong"),
            "abstained": stats.rate(n - len(placed) - len(reviewed), n), "wrong_among_placed": stats.rate(len(wrong), len(placed)) if placed else None,
            "cost_total": round(sum(r["cost"] for r in rows), 4),
            "calibration": stats.ece(probs, outs) if len(probs) >= 10 else None, "rows": rows}


def actions_of(verdicts: Mapping[str, Verdict]) -> dict[str, str]:
    """What geo-eval's Gate consumes: accept when placed, review when abstained."""
    return {c: ("accept" if (v.placement is not None and v.action == "accept") else "review") for c, v in verdicts.items()}


def labels_for_gate(scored: dict) -> dict[str, str]:
    """For the Gate's missed-error rule: a placed-wrong case is the thing that must not rise, so it is labelled
    'wrong' and its action was 'accept'; everything else is 'right'."""
    return {r["case"]: ("wrong" if r["outcome"] == "wrong" or r.get("would_be") == "wrong" else "right") for r in scored["rows"]}
