"""Draw a held-out benchmark of USGS 15' quadrangles by a fixed rule, never by looking at the sheets.

    python benchmarks/sample_usgs15.py --n 100 --seed 20261108 --out benchmarks/usgs15_heldout_v1.json

Rule (the whole of it):
1. Points uniform at random over the contiguous United States' bounding box (seeded, in order).
2. For each point, the USGS Historical Topographic Map Collection's GeoTIFFs at 1:62,500 whose catalogue bounding
   box is a 15' x 15' quadrangle containing the point. A point over the sea, Canada, Mexico or an area never mapped
   at 1:62,500 yields nothing and is skipped.
3. A quadrangle enters once, only with two or more scans, and never if it is in the development set (demo/cases.json).
4. Its two scans: if the scans span two or more publication years, two distinct years at random, then one scan of
   each year at random; otherwise two scans at random. All draws from one seeded generator, in point order.
5. Stop at n quadrangles.

The record for each case is what the catalogue says of the sheet: its nominal 15' bounds (the corners printed on
the sheet) and the 5' graticule interval. Nothing here opens an image or a georeference.
"""
from __future__ import annotations

import argparse
import json
import random
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

API = "https://tnmaccess.nationalmap.gov/api/v1/products"
BASE = "https://prd-tnm.s3.amazonaws.com/StagedProducts/Maps/HistoricalTopo/GeoTIFF/"
CONUS = (-124.7, 24.5, -66.9, 49.4)
ROOT = Path(__file__).resolve().parents[1]


def query(pt, retries: int = 4):
    lon, lat = pt
    q = urllib.parse.urlencode({"datasets": "Historical Topographic Maps", "prodFormats": "GeoTIFF", "max": 200,
                                "bbox": f"{lon - 0.001},{lat - 0.001},{lon + 0.001},{lat + 0.001}"})
    for i in range(retries):
        try:
            with urllib.request.urlopen(f"{API}?{q}", timeout=60) as r:
                return json.load(r).get("items", [])
        except Exception:                                   # noqa: BLE001  the API is flaky under load: retry, then give up on the point
            time.sleep(2 * (i + 1))
    return None


def quad_scans(items, pt):
    """The 15' 1:62,500 quadrangle holding the point, and its scans (url, year)."""
    lon, lat = pt
    quads: dict[tuple, list] = {}
    for it in items:
        url = it["downloadURL"]
        if "_62500_geo.tif" not in url or not url.startswith(BASE):
            continue
        b = it["boundingBox"]
        if abs(b["maxX"] - b["minX"] - 0.25) > 1e-6 or abs(b["maxY"] - b["minY"] - 0.25) > 1e-6:
            continue
        if not (b["minX"] <= lon < b["maxX"] and b["minY"] <= lat < b["maxY"]):
            continue
        key = (round(b["minX"], 6), round(b["minY"], 6), round(b["maxX"], 6), round(b["maxY"], 6))
        name = it["title"].split("Quadrangle for ")[-1].rsplit(" ", 1)[0]
        quads.setdefault(key, []).append((url[len(BASE):], int(it["publicationDate"][:4]), name))
    return quads


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=20261108)
    ap.add_argument("--points", type=int, default=3000, help="how many random points to draw at most")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    pts = [(round(rng.uniform(CONUS[0], CONUS[2]), 5), round(rng.uniform(CONUS[1], CONUS[3]), 5)) for _ in range(a.points)]
    dev = json.loads((ROOT / "demo" / "cases.json").read_text())
    dev_bounds = {tuple(round(v, 6) for v in c["bounds"]) for c in dev["cases"] if not c.get("control")}
    pick = random.Random(a.seed + 1)
    cases, seen, stats = [], set(dev_bounds), {"points": 0, "no_answer": 0, "no_quad": 0, "one_scan": 0, "dev_or_seen": 0}
    with ThreadPoolExecutor(6) as ex:
        for pt, items in zip(pts, ex.map(query, pts)):           # map keeps point order: the draw is deterministic
            stats["points"] += 1
            if items is None:
                stats["no_answer"] += 1; continue
            quads = quad_scans(items, pt)
            if not quads:
                stats["no_quad"] += 1; continue
            key, scans = next(iter(quads.items()))
            if key in seen:
                stats["dev_or_seen"] += 1; continue
            scans = sorted(set(scans))
            if len(scans) < 2:
                stats["one_scan"] += 1; seen.add(key); continue
            seen.add(key)
            years = sorted({y for _, y, _ in scans})
            if len(years) >= 2:
                ya, yb = pick.sample(years, 2)
                two = [pick.choice([s for s in scans if s[1] == ya]), pick.choice([s for s in scans if s[1] == yb])]
            else:
                two = pick.sample(scans, 2)
            two.sort(key=lambda s: s[1])
            name = scans[0][2]
            cases.append({"id": f"q{len(cases) + 1:03d}", "sheet": f"{name} (15')", "bounds": list(key), "interval_min": 5,
                          "scans": [s[0] for s in two], "years": [s[1] for s in two], "point": list(pt)})
            if len(cases) >= a.n:
                break
    out = {"about": "Held-out USGS 15' quadrangles drawn by benchmarks/sample_usgs15.py (rule in its docstring); never used "
                    "to set any threshold. Same format as demo/cases.json.",
           "rule": {"seed": a.seed, "n": a.n, "conus": CONUS, "scale": "1:62500", "extent_deg": 0.25,
                    "excluded": "the development quadrangles in demo/cases.json"},
           "draw": stats, "base_url": BASE, "cases": cases}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1))
    print(json.dumps(stats), f"-> {len(cases)} cases in {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
