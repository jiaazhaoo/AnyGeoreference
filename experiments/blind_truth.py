"""Reference truth for blind inputs that have no archive georeference: a plain proper similarity fitted by RANSAC to the
sheet's labels that are unique within a region given by hand (outside knowledge: where the map is), from OS Open Names
(places, or named roads for street plans). Different method from the system's matchers; the same gazetteer, so it is
a weaker truth than an archive's and is used only for regression (does a change make a known sheet go wrong), with its
own residual reported. Output: truth points (5x5 grid over the sheet, px -> EPSG:27700) per sheet."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

DB = "/data/reference/base-data/opname_csv_gb/os_open_names_uk.sqlite"
READS = Path("/data/lab/projects/georeference-anything/claude_reads")
# sheet id -> (region box in EPSG:27700, Open Names types used, cue kinds used, RANSAC tolerance m, image size)
SHEETS = {
    "thames_chart_1900": ((545000, 168000, 570000, 185000), ("populatedPlace", "hydrography", "landform", "landcover", "other"), ("place", "landmark"), 600),
    "osd_norwich": ((590000, 285000, 650000, 335000), ("populatedPlace",), ("place", "landmark"), 1500),
    "norwich_1884_left": ((618000, 304000, 628000, 314000), ("transportNetwork",), ("road",), 150),
    "norwich_1884_right": ((618000, 304000, 628000, 314000), ("transportNetwork",), ("road",), 150),
    "sheffield_1823_plan": ((430000, 382000, 440000, 392000), ("transportNetwork",), ("road",), 150),
    "gleadless_valley_osm": ((432000, 379000, 442000, 389000), ("transportNetwork",), ("road",), 150),
}


def pairs(sheet, box, types, kinds):
    rd = json.load(open(READS / f"{sheet}.json"))
    con = sqlite3.connect(DB); out = []
    q = f"SELECT GEOMETRY_X, GEOMETRY_Y FROM open_names WHERE NAME1=? COLLATE NOCASE AND TYPE IN ({','.join('?' * len(types))}) AND GEOMETRY_X BETWEEN ? AND ? AND GEOMETRY_Y BETWEEN ? AND ?"
    for c in rd["cues"]:
        if c["kind"] not in kinds:
            continue
        names = {c["text"], c["text"].title()}
        for suf, full in ((" St.", " Street"), (" St", " Street"), (" Rd", " Road"), (" La.", " Lane")):
            names |= {n.replace(suf, full) for n in list(names) if n.endswith(suf)}
        rows = set()
        for n in names:
            rows |= set(con.execute(q, (n, *types, box[0], box[2], box[1], box[3])).fetchall())
        if len(rows) == 1 or (len(rows) > 1 and np.ptp(np.array(list(rows), float), axis=0).max() < 400):   # one place, or one street's sections
            P = np.array(list(rows), float).mean(0)
            x0, y0, x1, y1 = c["bbox"]; out.append((c["text"], (x0 + x1) / 2, (y0 + y1) / 2, P[0], P[1]))
    return out


def fit(A, B):
    a = A * [1, -1]; ma, mb = a.mean(0), B.mean(0)
    za, zb = (a - ma) @ [1, 1j], (B - mb) @ [1, 1j]
    s = (np.conj(za) @ zb) / (np.conj(za) @ za)
    return lambda P: (((np.asarray(P) * [1, -1] - ma) @ [1, 1j]) * s) + (mb @ [1, 1j]), s


def ransac(pp, tol, rng=np.random.default_rng(0)):
    A = np.array([p[1:3] for p in pp]); B = np.array([p[3:5] for p in pp]); best = None
    for _ in range(4000):
        i = rng.choice(len(pp), 2, replace=False); f, _ = fit(A[i], B[i])
        inl = np.abs(f(A) - B @ [1, 1j]) < tol
        if best is None or inl.sum() > best.sum():
            best = inl
    f, s = fit(A[best], B[best])
    return f, s, int(best.sum()), float(np.median(np.abs(f(A[best]) - B[best] @ [1, 1j])))


def main(out_path):
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    src = {"thames_chart_1900": "blind2/src/thames_chart_1900.jpg", "osd_norwich": "blind2/src/osd_norwich.jpg",
           "norwich_1884_left": "blind2/src/norwich_1884_left.jpg", "norwich_1884_right": "blind2/src/norwich_1884_right.jpg",
           "sheffield_1823_plan": "blind/commons/Sheffield_1823_plan.jpg", "gleadless_valley_osm": "blind/commons/Gleadless_Valley_OSM.png"}
    root = Path("/data/lab/projects/georeference-anything"); out = {}
    for sid, (box, types, kinds, tol) in SHEETS.items():
        pp = pairs(sid, box, types, kinds)
        if len(pp) < 4:
            print(sid, "too few unique labels", len(pp)); continue
        f, s, n_in, med = ransac(pp, tol)
        w, h = Image.open(root / src[sid]).size
        gx, gy = np.meshgrid(np.linspace(0.1, 0.9, 5), np.linspace(0.1, 0.9, 5))
        P = f(np.c_[gx.ravel() * w, gy.ravel() * h])
        out[sid] = {"crs": "EPSG:27700", "method": "RANSAC proper similarity over labels unique in a hand-given region (Open Names)",
                    "labels": len(pp), "inliers": n_in, "residual_median_m": round(med, 1), "m_per_px": round(abs(s), 3),
                    "rotation_deg": round(float(np.degrees(np.angle(s))), 1), "width": w, "height": h,
                    "truth_points": [{"x": float(x), "y": float(y), "X": float(p.real), "Y": float(p.imag)} for x, y, p in zip(gx.ravel() * w, gy.ravel() * h, P)]}
        print(sid, f"{n_in}/{len(pp)} inliers, median {med:.0f} m, {abs(s):.2f} m/px, rot {np.degrees(np.angle(s)):.1f}")
    Path(out_path).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
