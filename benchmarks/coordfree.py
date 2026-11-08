"""A coordinate-free benchmark: extracts of truth-bearing map scans with every printed coordinate cut away.

The other benchmarks hand the system the sheet's corner coordinates and its graticule interval; placing a sheet is
then reading marks and fitting. This one hands it an image and, at most, a few words a catalogue would hold. Each
case is a window inside the map body of a scan whose georeference is known (a USGS GeoTIFF, or a scan registered by
control points), so the truth comes for free and is exact to the archive's own error.

    python benchmarks/coordfree.py draw  --from benchmarks/usgs15_heldout_v4.json --seed 20261121 --n 40 --out benchmarks/coordfree_dev_usgs.json
    python benchmarks/coordfree.py build benchmarks/coordfree_dev_usgs.json
    python benchmarks/coordfree.py score benchmarks/coordfree_dev_usgs.json results.json

Draw rule (the whole of it; it never opens an image or a georeference):
1. The source cases in file order, controls skipped; stop at n.
2. One of the case's scans, uniformly at random.
3. A window inside the map body: width and height each a uniform fraction 0.40-0.70 of the map body, its position
   uniform over the places it fits. The map body is the record's sheet bounds shrunk by 8 % on every side, so the
   neatline, the margin, its coordinate labels and every edge tick are outside every window.
4. Hints, three tiers, each run separately: "none"; "region" (the state, or the country where the catalogue states no
   finer unit); "title" (the place in the sheet's title, as a catalogue would give it, with any sheet number or scale
   removed: a sheet index is a coordinate). The title place need not lie inside the window.
All random choices come from one generator seeded with --seed, in case order.

What a system under test may read: the window image and one hint string (see `inputs`). Everything else in a case
(source scan, window, sheet bounds) is for building and scoring only, and the truth files live apart from the images.
The window keeps north up and the scan's own resolution (reduced to 3000 px on its long side); interior graticule
crosses and tick marks without labels stay, as they do on any extract of a survey sheet.

Scoring: a run answers each (case, tier) with an action (accept / review / abstain) and, unless it abstains, control
pairs [x, y, lon, lat] in window pixels and WGS84. The scorer fits the pairs (affine, or poly2 from 10 pairs) and
measures the distance to the truth on a 7 x 7 grid over the window. Right = the worst grid point within 100 m, as in
the other benchmarks. Placements that are not right are still graded by median distance (within 1 km, within
10 km): finding the area is a capability of its own.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TIERS = ("none", "region", "title")
SHRINK = 0.08                  # map body = sheet bounds shrunk by this fraction on every side
WINDOW = (0.40, 0.70)          # window side as a fraction of the map body
LONG_SIDE = 3000               # window images are reduced to this many pixels on the long side
GRID = 7
RIGHT_M = 100.0

US_STATES = {
    "AL": "Alabama", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado", "CT": "Connecticut",
    "DE": "Delaware", "FL": "Florida", "GA": "Georgia", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts",
    "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska",
    "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "DC": "District of Columbia",
}


# ---------------------------------------------------------------- hints

def hints_for(case: dict) -> dict:
    """The region and title tiers from the catalogue's sheet title, with sheet numbers and scales removed."""
    sheet = case.get("sheet", "")
    if case.get("datum") == "EPSG:4314" or sheet.startswith("TK25"):          # German 1:25,000: "TK25 5051 (Section Sebnitz)"
        m = re.search(r"\((.*)\)", sheet)                                     # "(Meßtischblatt 288 : Strelln, 1874)"
        place = (m.group(1) if m else sheet).split(":")[-1].split(",")[0]
        place = re.sub(r"\b(Section|Sektion|Blatt|Messtischblatt|Meßtischblatt)\b|\(.*?\)|\[.*?\]|[\d=]+", " ", place)
        place = re.sub(r"\s+", " ", place).strip(" -,")
        return {"region": "Germany", "title": f"{place}, Germany" if place else "Germany"}
    m = re.match(r"^(.*?),\s*([A-Z]{2})\b", sheet)                             # USGS: "Harrisville, WV (15')"
    if m:
        state = US_STATES.get(m.group(2), m.group(2))
        return {"region": f"{state}, United States", "title": f"{m.group(1).strip()}, {state}, United States"}
    place = re.sub(r"\(.*?\)|\d+", "", sheet).strip(" -,")
    return {"region": "", "title": place}


def hint_text(case: dict, tier: str) -> str:
    return "" if tier == "none" else case["hints"][tier]


# ---------------------------------------------------------------- draw

def draw(src_file: str, seed: int, n: int | None, prefix: str) -> dict:
    src = json.loads(Path(src_file).read_text())
    rng = random.Random(seed)
    cases = []
    for c in src["cases"]:
        if c.get("control"):
            continue
        k = rng.randrange(len(c["scans"]))
        fw, fh = rng.uniform(*WINDOW), rng.uniform(*WINDOW)
        ox, oy = rng.random(), rng.random()
        cases.append({"id": f"{prefix}{len(cases) + 1:03d}", "source_case": c["id"], "scan_index": k, "scan": c["scans"][k],
                      "window": [round(fw, 4), round(fh, 4), round(ox, 4), round(oy, 4)], "hints": hints_for(c)})
        if n and len(cases) >= n:
            break
    return {"about": "Coordinate-free cases drawn by benchmarks/coordfree.py (rule in its docstring) from the source "
                     "file below. A system under test reads only the window image and one hint string.",
            "rule": {"seed": seed, "n": n, "shrink": SHRINK, "window": WINDOW, "long_side": LONG_SIDE, "tiers": TIERS},
            "source": src_file, "cases": cases}


# ---------------------------------------------------------------- build

def _source_case(src: dict, cid: str) -> dict:
    return next(c for c in src["cases"] if c["id"] == cid)


def _scan_path(src: dict, sc: dict, k: int) -> Path:
    from demo.run_demo import fetch
    rel = sc["scans"][k]
    if src.get("data_dir"):
        return fetch(None, rel, ROOT / src["data_dir"])
    return fetch(src.get("base_url"), rel, ROOT / "benchmarks" / "data")


def _truth(src: dict, sc: dict, k: int, path: Path):
    from demo.run_demo import Truth
    pairs = (sc.get("truth") or [None] * len(sc["scans"]))[k]
    return Truth(path, pairs)


def window_px(truth, sc: dict, window) -> tuple[int, int, int, int]:
    """The window in scan pixels: the record's bounds through the truth, shrunk to the map body, then the drawn part."""
    from pyproj import Transformer
    w, s, e, n = sc["bounds"]
    corners = np.array([[w, n], [e, n], [e, s], [w, s]], float)
    to_wgs = Transformer.from_crs(sc.get("datum", "EPSG:4267"), "EPSG:4326", always_xy=True)
    px = truth.ll_to_px(np.c_[to_wgs.transform(corners[:, 0], corners[:, 1])])
    x0, y0 = px.min(0)
    x1, y1 = px.max(0)
    bw, bh = x1 - x0, y1 - y0
    x0, x1, y0, y1 = x0 + SHRINK * bw, x1 - SHRINK * bw, y0 + SHRINK * bh, y1 - SHRINK * bh
    fw, fh, ox, oy = window
    ww, wh = fw * (x1 - x0), fh * (y1 - y0)
    left, top = x0 + ox * (x1 - x0 - ww), y0 + oy * (y1 - y0 - wh)
    left, top = max(0.0, left), max(0.0, top)
    right, bottom = min(float(truth.W), left + ww), min(float(truth.H), top + wh)
    return int(round(left)), int(round(top)), int(round(right)), int(round(bottom))


def grid(w: int, h: int, n: int = GRID) -> np.ndarray:
    xs, ys = np.meshgrid(np.linspace(0.05 * w, 0.95 * w, n), np.linspace(0.05 * h, 0.95 * h, n))
    return np.c_[xs.ravel(), ys.ravel()]


def build(case_file: str, out: Path | None = None, only: list[str] | None = None) -> Path:
    """Window images in <out>/images and truth in <out>/truth (never read by a system under test)."""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    cf = json.loads(Path(case_file).read_text())
    src = json.loads((ROOT / cf["source"]).read_text())
    out = out or ROOT / "benchmarks" / "data" / "coordfree" / Path(case_file).stem
    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "truth").mkdir(parents=True, exist_ok=True)
    for c in cf["cases"]:
        if only and c["id"] not in only:
            continue
        img_p, tru_p = out / "images" / f"{c['id']}.jpg", out / "truth" / f"{c['id']}.json"
        if img_p.exists() and tru_p.exists():
            continue
        sc = _source_case(src, c["source_case"])
        path = _scan_path(src, sc, c["scan_index"])
        truth = _truth(src, sc, c["scan_index"], path)
        l, t, r, b = window_px(truth, sc, c["window"])
        with Image.open(path) as im:
            crop = im.convert("RGB").crop((l, t, r, b))
        f = min(1.0, LONG_SIDE / max(crop.size))
        if f < 1.0:
            crop = crop.resize((round(crop.size[0] * f), round(crop.size[1] * f)), Image.LANCZOS)
        crop.save(img_p, "JPEG", quality=90)                    # no EXIF, no georeference: pixels only
        w, h = crop.size
        g = grid(w, h)
        ll = truth.px_to_ll(np.c_[l + g[:, 0] / f, t + g[:, 1] / f])
        tru_p.write_text(json.dumps({"id": c["id"], "size": [w, h], "window_px": [l, t, r, b], "scale": round(f, 6),
                                     "truth_source": truth.kind, "grid_px": g.round(2).tolist(),
                                     "grid_ll": ll.round(7).tolist()}))
        print(f"  {c['id']}: {w}x{h} from {Path(path).name}", flush=True)
    return out


def inputs(case_file: str, out: Path | None = None):
    """What a system under test is given: (case id, tier, window image path, hint string). Nothing else."""
    cf = json.loads(Path(case_file).read_text())
    out = out or ROOT / "benchmarks" / "data" / "coordfree" / Path(case_file).stem
    for c in cf["cases"]:
        for tier in TIERS:
            yield c["id"], tier, out / "images" / f"{c['id']}.jpg", hint_text(c, tier)


# ---------------------------------------------------------------- score

def placement_error(pairs: list, truth: dict) -> dict:
    """Distance (m) from a placement, given as control pairs [x, y, lon, lat], to the truth on the window's grid."""
    from ga.primitives.generic import apply_transform, fit_transform
    P = np.asarray(pairs, float)
    model = "poly2" if len(P) >= 10 else "affine"
    coef, _ = fit_transform(P[:, :2], P[:, 2:], model)
    g, t = np.asarray(truth["grid_px"], float), np.asarray(truth["grid_ll"], float)
    o = apply_transform(coef, g, model)
    k = 111320.0 * math.cos(math.radians(float(t[:, 1].mean())))
    d = np.hypot((o[:, 0] - t[:, 0]) * k, (o[:, 1] - t[:, 1]) * 110574.0)
    return {"median_m": round(float(np.median(d)), 1), "max_m": round(float(d.max()), 1)}


def score(case_file: str, results: dict, out: Path | None = None) -> dict:
    """results: {case id: {tier: {"action": ..., "pairs": [[x, y, lon, lat], ...]}}}. A missing answer is an abstain."""
    cf = json.loads(Path(case_file).read_text())
    out = out or ROOT / "benchmarks" / "data" / "coordfree" / Path(case_file).stem
    rows, tally = [], {t: {"cases": 0, "accepted right": 0, "accepted wrong": 0, "review": 0, "abstain": 0,
                           "placed": 0, "within 1 km": 0, "within 10 km": 0} for t in TIERS}
    for c in cf["cases"]:
        truth = json.loads((out / "truth" / f"{c['id']}.json").read_text())
        for tier in TIERS:
            a = (results.get(c["id"]) or {}).get(tier) or {"action": "abstain"}
            T = tally[tier]; T["cases"] += 1
            row = {"id": c["id"], "tier": tier, "action": a["action"], "why": a.get("why", "")}
            if a["action"] != "abstain" and a.get("pairs") and len(a["pairs"]) >= 3:
                e = placement_error(a["pairs"], truth)
                row.update(e, right=e["max_m"] <= RIGHT_M)
                T["placed"] += 1
                T["within 1 km"] += e["median_m"] <= 1000
                T["within 10 km"] += e["median_m"] <= 10000
                if a["action"] == "accept":
                    T["accepted right" if row["right"] else "accepted wrong"] += 1
                else:
                    T["review"] += 1
            else:
                row["action"] = "abstain"; T["abstain"] += 1
            rows.append(row)
    return {"tally": tally, "rows": rows}


# ---------------------------------------------------------------- cli

def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draw"); d.add_argument("--from", dest="src", required=True); d.add_argument("--seed", type=int, required=True)
    d.add_argument("--n", type=int); d.add_argument("--prefix", default="c"); d.add_argument("--out", required=True)
    b = sub.add_parser("build"); b.add_argument("cases"); b.add_argument("--only", nargs="*")
    s = sub.add_parser("score"); s.add_argument("cases"); s.add_argument("results"); s.add_argument("--out")
    a = ap.parse_args()
    if a.cmd == "draw":
        res = draw(a.src, a.seed, a.n, a.prefix)
        Path(a.out).write_text(json.dumps(res, indent=1, ensure_ascii=False))
        print(f"{len(res['cases'])} cases -> {a.out}")
    elif a.cmd == "build":
        print(build(a.cases, only=a.only))
    else:
        res = score(a.cases, json.loads(Path(a.results).read_text()))
        text = json.dumps(res, indent=1)
        Path(a.out).write_text(text) if a.out else print(json.dumps(res["tally"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
