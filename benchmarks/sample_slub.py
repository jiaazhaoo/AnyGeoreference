"""A second map family for the held-out benchmark: Saxon and German 1:25,000 sheets (Messtischblaetter and
Aequidistantenkarten) from the SLUB Virtual Map Forum (Dresden), drawn by a fixed rule.

    python benchmarks/sample_slub.py --n 50 --seed 20261111 --out benchmarks/slub_heldout_v1.json

What differs from the USGS family, on purpose: another country and survey, another datum (Bessel ellipsoid; the
record states DHDN, EPSG:4314), longitudes printed east of Ferro on older sheets, a 10' x 6' sheet, a double frame
line and minute divisions along the edges, another printer, scanner and library, and truth made by other people.

Rule:
1. All georeferenced sheets of types mtb (Messtischblatt) and ae (Aequidistantenkarte) in the SLUB search index that
   offer the library's rectified GeoTIFF for download (needed for truth; a metadata field, no image is opened).
2. Each sheet's nominal TK25 cell (rows of 6' from 56 N, columns of 10' from 5 50' E Greenwich): the cell holding the
   centre of the catalogue footprint, kept only when the footprint matches the cell within 1' on every side (a
   standard sheet). The footprint is used for this and nothing else; the record carries the cell, which is what the
   sheet prints at its corners.
3. Cells with two or more georeferenced scans of different years; cells drawn at random (seeded); two scans per cell
   by the same draw as the USGS sampler (two distinct years, one scan of each).
4. Input: the original, unrectified scan, stitched from the library's Zoomify tiles at the level nearest 4500 px wide
   (about 0.1 mm of paper per pixel, like the USGS scans), so that the test is about the family, not resolution.
5. Truth: the scan registered to the library's own rectified GeoTIFF (WCS, EPSG:4326): SIFT on both at one working
   scale, RANSAC, then scan pixels -> lon/lat as poly2 plus a smoothed thin-plate spline (the library rectifies with
   splines; poly2 alone misses by about 20 m). Pairs that a fit without them does not predict are dropped; kept only
   with >= 60 pairs and a 4-fold held-out error p95 within 25 m. The pairs and that error are stored in the case
   file. Truth is read by the scorer, never by the loop.
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import math
import random
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

try:                                   # verify TLS against the system's trust store (as curl does); never skip verification
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SEARCH = "https://search.kartenforum.slub-dresden.de/vk20/_search"
AGENT = "AnyGeoreference/0.1 (research benchmark; https://github.com/jiaazhaoo/AnyGeoreference)"
ROW0, COL0, DLAT, DLON = 56.0, 5 + 50 / 60, 6 / 60, 10 / 60


def _get(url: str, data: bytes | None = None, headers: dict | None = None, retries: int = 5, timeout: int = 120) -> bytes:
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": AGENT, **(headers or {})})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:                                              # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"{url[:100]}: {last}")


def records() -> list[dict]:
    q = {"size": 9000, "query": {"bool": {"must": [{"terms": {"map_type": ["mtb", "ae"]}}, {"term": {"has_georeference": True}}]}},
         "_source": ["map_id", "file_name", "title_long", "time_published", "zoomify_url", "online_resources", "geometry", "map_type", "map_scale"]}
    d = json.loads(_get(SEARCH, json.dumps(q).encode(), {"Content-Type": "application/json"}))
    return [h["_source"] for h in d["hits"]["hits"]]


def cell_of(rec: dict):
    g = rec.get("geometry")
    g = ast.literal_eval(g) if isinstance(g, str) else g
    if not g or g.get("type") != "Polygon":
        return None
    xy = np.array(g["coordinates"][0], float)
    w, s, e, n = xy[:, 0].min(), xy[:, 1].min(), xy[:, 0].max(), xy[:, 1].max()
    row = math.floor((ROW0 - (s + n) / 2) / DLAT); col = math.floor(((w + e) / 2 - COL0) / DLON)
    cn = ROW0 - row * DLAT; cs = cn - DLAT; cw = COL0 + col * DLON; ce = cw + DLON
    if max(abs(n - cn), abs(s - cs), abs(w - cw), abs(e - ce)) > 1 / 60:
        return None
    return (round(cw, 6), round(cs, 6), round(ce, 6), round(cn, 6)), f"{row:02d}{col + 1:02d}"


def zoomify(url: str, target_w: int = 4500) -> np.ndarray:
    """Stitch a Zoomify pyramid level whose width is nearest target_w. Returns RGB."""
    import cv2
    import xml.etree.ElementTree as ET
    base = url.rsplit("/", 1)[0]
    p = ET.fromstring(_get(url)).attrib
    W, H, T = int(p["WIDTH"]), int(p["HEIGHT"]), int(p.get("TILESIZE", 256))
    dims = [(W, H)]
    while dims[-1][0] > T or dims[-1][1] > T:
        w, h = dims[-1]
        dims.append(((w + 1) // 2, (h + 1) // 2))
    dims = dims[::-1]                                                       # level 0 = smallest
    counts = [math.ceil(w / T) * math.ceil(h / T) for w, h in dims]
    lvl = min(range(len(dims)), key=lambda i: abs(dims[i][0] - target_w))
    w, h = dims[lvl]; nx, ny = math.ceil(w / T), math.ceil(h / T)
    before = sum(counts[:lvl])
    img = np.full((h, w, 3), 255, np.uint8)
    def tile(ij):
        i, j = ij
        k = before + j * nx + i
        b = _get(f"{base}/TileGroup{k // 256}/{lvl}-{i}-{j}.jpg")
        t = cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR)
        return i, j, t
    with ThreadPoolExecutor(4) as ex:
        for i, j, t in ex.map(tile, [(i, j) for j in range(ny) for i in range(nx)]):
            if t is not None:
                img[j * T:j * T + t.shape[0], i * T:i * T + t.shape[1]] = t[..., ::-1]
    return img


def _download(rec: dict):
    res = rec.get("online_resources"); res = ast.literal_eval(res) if isinstance(res, str) else (res or [])
    return next((r["url"] for r in res if r.get("type") == "download"), None)


def truth_pairs(rgb: np.ndarray, rec: dict, max_pairs: int = 400):
    """Scan pixels <-> lon/lat (EPSG:4326) by registering the scan to the library's rectified GeoTIFF."""
    import cv2
    import rasterio
    url = _download(rec)
    if not url:
        return None, "no rectified download"
    u = urllib.parse.urlsplit(url); q = dict(urllib.parse.parse_qsl(u.query))
    W, H = int(q.pop("WIDTH")), int(q.pop("HEIGHT"))                      # WIDTH/HEIGHT are ignored; WCS 2.0 scaling works
    q["SCALEFACTOR"] = f"{min(1.0, 3200 / max(W, H)):.4f}"
    blob = _get(urllib.parse.urlunsplit(u._replace(query=urllib.parse.urlencode(q))), timeout=300)
    with rasterio.open(io.BytesIO(blob)) as ds:
        ref = ds.read([1, 2, 3]).transpose(1, 2, 0) if ds.count >= 3 else np.repeat(ds.read(1)[..., None], 3, -1)
        T = ds.transform
    s2 = 3000 / max(ref.shape[:2])                                          # both images at one working scale
    ref = cv2.resize(np.ascontiguousarray(ref), None, fx=s2, fy=s2, interpolation=cv2.INTER_AREA)
    T = T * T.scale(1 / s2)
    g1 = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY); g2 = cv2.cvtColor(np.ascontiguousarray(ref), cv2.COLOR_RGB2GRAY)
    s1 = 3000 / max(g1.shape)
    a = cv2.resize(g1, None, fx=s1, fy=s1, interpolation=cv2.INTER_AREA)
    sift = cv2.SIFT_create(nfeatures=12000)
    ka, da = sift.detectAndCompute(a, None); kb, db = sift.detectAndCompute(g2, (g2 > 0).astype(np.uint8) * 255)
    if da is None or db is None:
        return None, "no features"
    m = [p for p, q_ in (x for x in cv2.BFMatcher(cv2.NORM_L2).knnMatch(da, db, k=2) if len(x) == 2) if p.distance < 0.75 * q_.distance]
    if len(m) < 60:
        return None, f"{len(m)} matches"
    pa = np.float32([ka[x.queryIdx].pt for x in m]) / s1; pb = np.float32([kb[x.trainIdx].pt for x in m])
    _, inl = cv2.findHomography(pa, pb, cv2.RANSAC, 6.0 / s1)
    if inl is None or inl.sum() < 60:
        return None, f"{0 if inl is None else int(inl.sum())} inliers"
    pa, pb = pa[inl.ravel() == 1], pb[inl.ravel() == 1]
    lon = T.c + T.a * (pb[:, 0] + 0.5) + T.b * (pb[:, 1] + 0.5); lat = T.f + T.d * (pb[:, 0] + 0.5) + T.e * (pb[:, 1] + 0.5)
    from ga.primitives.generic import cross_validated_error
    ll = np.c_[lon, lat].astype(float); pa = pa.astype(float)
    k = (111320 * math.cos(math.radians(float(lat.mean()))), 110574.0)
    for _ in range(2):                                                      # drop pairs the others do not predict
        e = cross_validated_error(pa, ll, k)
        keep = e <= max(20.0, 4 * np.median(e))
        pa, ll = pa[keep], ll[keep]
    e = cross_validated_error(pa, ll, k)
    med, p95 = float(np.median(e)), float(np.percentile(e, 95))
    if len(pa) < 60 or p95 > 25:
        return None, f"{len(pa)} pairs, held-out error p95 {p95:.1f} m"
    idx = np.random.default_rng(0).permutation(len(pa))[:max_pairs]
    return {"crs": "EPSG:4326", "model": "poly2+tps", "pairs": [[round(float(x), 1), round(float(y), 1), round(float(lo), 7), round(float(la), 7)]
                                         for (x, y), (lo, la) in zip(pa[idx], ll[idx])],
            "heldout_median_m": round(med, 1), "heldout_p95_m": round(p95, 1), "n": int(len(pa))}, None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=20261111)
    ap.add_argument("--out", required=True)
    ap.add_argument("--data", default=str(ROOT / "benchmarks" / "data" / "slub"))
    ap.add_argument("--exclude", nargs="*", default=[])
    a = ap.parse_args()
    import cv2
    recs = records()
    cells: dict = {}
    for r in recs:
        c = cell_of(r)
        if c and r.get("zoomify_url") and r.get("time_published") and _download(r):
            cells.setdefault(c, []).append(r)
    seen = set()
    for f in a.exclude:
        seen |= {tuple(c["bounds"]) for c in json.loads(Path(f).read_text())["cases"]}
    keys = sorted(k for k, v in cells.items() if len({x["time_published"][:4] for x in v}) >= 2 and k[0] not in seen)
    rng = random.Random(a.seed); rng.shuffle(keys)
    pick = random.Random(a.seed + 1)
    data = Path(a.data); data.mkdir(parents=True, exist_ok=True)
    cases, dropped = [], []
    for (bounds, sheet_no) in keys:
        if len(cases) >= a.n:
            break
        recs_ = sorted(cells[(bounds, sheet_no)], key=lambda r: r["map_id"])
        years = sorted({r["time_published"][:4] for r in recs_})
        ya, yb = pick.sample(years, 2)
        two = sorted([pick.choice([r for r in recs_ if r["time_published"][:4] == y]) for y in (ya, yb)], key=lambda r: r["time_published"])
        scans, truths, why = [], [], None
        for r in two:
            name = r["file_name"] + ".jpg"
            path = data / name
            try:
                if not path.exists():
                    rgb = zoomify(r["zoomify_url"])
                    cv2.imwrite(str(path), rgb[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, 92])
                rgb = cv2.imread(str(path))[..., ::-1].copy()
                t, why = truth_pairs(rgb, r)
            except Exception as e:                                          # noqa: BLE001
                t, why = None, f"{type(e).__name__}: {str(e)[:80]}"
            if t is None:
                break
            scans.append(name); truths.append(t)
        if len(scans) < 2:
            dropped.append({"sheet": sheet_no, "why": why}); print(f"drop {sheet_no}: {why}", flush=True); continue
        cases.append({"id": f"s{len(cases) + 1:03d}", "sheet": f"TK25 {sheet_no} ({two[0]['title_long'][:60]})", "bounds": list(bounds),
                      "interval_min": 1, "datum": "EPSG:4314", "scans": scans, "years": [int(r["time_published"][:4]) for r in two],
                      "map_ids": [r["map_id"] for r in two], "truth": truths})
        print(f"case {cases[-1]['id']} {sheet_no} {cases[-1]['years']} truth held-out p95 {[t['heldout_p95_m'] for t in truths]} m", flush=True)
    out = {"about": "Held-out second family: SLUB Virtual Map Forum 1:25,000 sheets, drawn by benchmarks/sample_slub.py (rule in its "
                    "docstring). Inputs are local stitched scans (data_dir); truth pairs map scan pixels to lon/lat (EPSG:4326).",
           "rule": {"seed": a.seed, "n": a.n, "types": ["mtb", "ae"], "cells_eligible": len(keys), "excluded": a.exclude},
           "dropped": dropped, "data_dir": "benchmarks/data/slub", "base_url": None, "cases": cases}
    Path(a.out).write_text(json.dumps(out, indent=1))
    print(f"{len(cases)} cases, {len(dropped)} dropped -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
