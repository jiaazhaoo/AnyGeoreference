"""The public demo: put USGS historical survey sheets on the Earth from their pixels, say how sure, say no when not.

    python demo/run_demo.py                 # downloads ~125 MB of public-domain scans once, runs every case, scores them
    python demo/run_demo.py --only boston_bay control_record_typo

Per case the record gives what a person reads off the sheet's corners (neatline bounds, graticule interval) and two
scans of that sheet. Each scan is placed on its own: graticule_marks -> control_point_fit (poly2) -> residual_check.
Then each placement is checked against the other scan's by map content (edition_agreement), and the kind's policy
decides accept / review / abstain. Only after that does the scorer open each GeoTIFF's own georeference (the truth)
and measure how far the placement is from it. No model, no API key, no GPU; deterministic.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ga import Decider, FixedPlan, Sheet, kinds, run          # noqa: E402
from ga.loop import step                                       # noqa: E402
from ga.model import digest_bytes                              # noqa: E402
from ga.primitives.generic import apply_transform              # noqa: E402
from ga.primitives.graticule import _fit_of                    # noqa: E402

KIND = "survey_graticule"
PLACE = ["graticule_marks", "control_point_fit", "residual_check", "basemap_agreement"]
RIGHT_M = 100.0          # a placement is right when no point of the map area is more than this from the archive's
DEFAULT_DATA = str(ROOT / "demo" / "data")


def fetch(base: str | None, rel: str, data: Path) -> Path:
    """A scan on disk: downloaded once from base + rel, or (base None) already in the data folder."""
    name = rel.split("/")[-1].replace("%20", "_")
    path = data / name
    if not path.exists():
        if not base:
            raise FileNotFoundError(f"{path} (this benchmark's scans are built by its sampler)")
        data.mkdir(parents=True, exist_ok=True)
        print(f"  downloading {name} ...", flush=True)
        tmp = path.with_suffix(".part")
        urllib.request.urlretrieve(base + rel, tmp)
        tmp.rename(path)
    return path


def sheet_for(path: Path, case: dict, bounds) -> Sheet:
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    with Image.open(path) as im:
        w, h = im.size
    with open(path, "rb") as f:
        head = f.read(1 << 20)
    record = {"bounds": list(bounds), "interval_min": case["interval_min"]}
    if case.get("datum"):
        record["datum"] = case["datum"]
    return Sheet(path.stem, "historical_map", str(path), digest_bytes(head), record, {"width": w, "height": h})


class Truth:
    """Scan pixels <-> WGS84 lon/lat by the archive's georeference: a GeoTIFF's own transform, or control points
    stored in the case (registered to the archive's rectified map). Read by the scorer only."""
    def __init__(self, path: Path, pairs: dict | None = None):
        from pyproj import Transformer
        if pairs:
            from ga.primitives.generic import fit_transform
            P = np.array(pairs["pairs"], float)
            self.fwd, _ = fit_transform(P[:, :2], P[:, 2:], "poly2")
            self.inv, _ = fit_transform(P[:, 2:], P[:, :2], "poly2")
            self.kind = f"control points (fit {pairs.get('rms_m')} m)"
            from PIL import Image
            Image.MAX_IMAGE_PIXELS = None
            with Image.open(path) as im:
                self.W, self.H = im.size
            self.geotiff = None
        else:
            import rasterio
            with rasterio.open(path) as ds:
                self.geotiff, self.W, self.H, crs = ds.transform, ds.width, ds.height, ds.crs
            self.to_wgs = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
            self.from_wgs = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
            self.kind = "GeoTIFF transform"

    def px_to_ll(self, px: np.ndarray) -> np.ndarray:
        if self.geotiff is None:
            return apply_transform(self.fwd, px, "poly2")
        T = self.geotiff
        x = T.c + T.a * (px[:, 0] + 0.5) + T.b * (px[:, 1] + 0.5); y = T.f + T.d * (px[:, 0] + 0.5) + T.e * (px[:, 1] + 0.5)
        return np.c_[self.to_wgs.transform(x, y)]

    def ll_to_px(self, ll: np.ndarray) -> np.ndarray:
        if self.geotiff is None:
            return apply_transform(self.inv, ll, "poly2")
        x, y = self.from_wgs.transform(ll[:, 0], ll[:, 1])
        inv = ~self.geotiff
        return np.array([inv * (a, b) for a, b in zip(x, y)]) - 0.5


def truth_error(truth: Truth, hyp, n: int = 7) -> dict:
    """Distance (m) between the placement and the archive's georeference on an n x n grid over the map area (the
    central part of the scan, clear of the collar), both in WGS84: the placement is moved from its own datum."""
    from pyproj import Transformer
    W, H = truth.W, truth.H
    xs, ys = np.meshgrid(np.linspace(0.15 * W, 0.85 * W, n), np.linspace(0.12 * H, 0.88 * H, n))
    px = np.c_[xs.ravel(), ys.ravel()]
    t = truth.px_to_ll(px)
    coeffs, model = _fit_of(hyp)
    o = apply_transform(coeffs, px, model)
    o = np.c_[Transformer.from_crs(hyp.crs, "EPSG:4326", always_xy=True).transform(o[:, 0], o[:, 1])]
    k = 111320.0 * math.cos(math.radians(float(np.mean(t[:, 1]))))
    d = np.hypot((o[:, 0] - t[:, 0]) * k, (o[:, 1] - t[:, 1]) * 110574.0)
    return {"median_m": round(float(np.median(d)), 1), "max_m": round(float(d.max()), 1), "centre_m": round(float(d[len(d) // 2]), 1)}


def overlay(path: Path, state, case: dict, out: Path, truth: Truth, scale: float = 0.2) -> str:
    """The scan reduced, with the graticule the loop read (red) and where the archive's georeference puts the
    printed graticule of the record's bounds (blue), the record's datum moved to WGS84."""
    import cv2
    from pyproj import Transformer
    from ga.primitives.graticule import gray_of
    img = cv2.cvtColor(cv2.resize(gray_of(str(path)), None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA), cv2.COLOR_GRAY2BGR)
    w, s, e, n = state.sheet.record["bounds"]; step_ = case["interval_min"] / 60
    datum = state.hypotheses[0].crs if state.hypotheses else state.sheet.record.get("datum", "EPSG:4267")
    to_wgs = Transformer.from_crs(datum, "EPSG:4326", always_xy=True)
    nodes = np.array([(w + i * step_, n - j * step_) for i in range(round((e - w) / step_) + 1) for j in range(round((n - s) / step_) + 1)])
    for x, y in truth.ll_to_px(np.c_[to_wgs.transform(nodes[:, 0], nodes[:, 1])]):
        cv2.circle(img, (int(x * scale), int(y * scale)), 9, (200, 90, 0), 2)
    for c in state.cues:
        x0, y0, x1, y1 = c.bbox
        cv2.drawMarker(img, (int((x0 + x1) / 2 * scale), int((y0 + y1) / 2 * scale)), (0, 0, 220), cv2.MARKER_CROSS, 16, 2)
    p = out / f"{case['id']}__{path.stem}.jpg"
    cv2.imwrite(str(p), img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return str(p.relative_to(out.parent)) if out.parent in p.parents else str(p)


def run_case(case: dict, base: str, data: Path, out: Path, reg, decider) -> list[dict]:
    paths = [fetch(base, rel, data) for rel in case["scans"]]
    bounds = case.get("bounds_per_scan") or [case["bounds"]] * len(paths)
    states = [run(sheet_for(p, case, b), reg, FixedPlan(PLACE)) for p, b in zip(paths, bounds)]
    for i, st in enumerate(states):
        sib = states[1 - i] if len(states) == 2 else None
        if st.hypotheses and sib is not None and sib.hypotheses:
            sev = {e.name: e for e in sib.evidence}
            meta = {**st.sheet.meta, "sibling": {"id": sib.sheet.id, "image": sib.sheet.image, "note": sib.hypotheses[0].note,
                                                 "basemap_agree": sev["basemap_agree"].value if "basemap_agree" in sev else None,
                                                 "basemap_note": sev["basemap_agree"].note if "basemap_agree" in sev else ""}}
            st.sheet = dataclasses.replace(st.sheet, meta=meta)
            step(st, reg, "edition_agreement")
    rows = []
    truths = case.get("truth") or [None] * len(paths)
    for p, st, tp in zip(paths, states, truths):
        v = decider.decide(st)
        ev = {e.name: e for e in st.evidence}
        row = {"case": case["id"], "scan": p.stem, "control": case.get("control"), "action": v.action, "why": v.why or "",
               "nodes": len(st.cues), "seconds": round(st.seconds, 2),
               "residual_m": round(ev["residual_rms"].value, 1) if "residual_rms" in ev else None,
               "graticule": ev["graticule_found"].note if "graticule_found" in ev else None,
               "editions": ev["editions_agree"].note if "editions_agree" in ev else None,
               "editions_agree": ev["editions_agree"].value if "editions_agree" in ev else None,
               "basemap": ev["basemap_agree"].note if "basemap_agree" in ev else None,
               "basemap_agree": ev["basemap_agree"].value if "basemap_agree" in ev else None,
               "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        if st.hypotheses:
            truth = Truth(p, tp)
            row["truth"] = truth_error(truth, st.hypotheses[0])
            row["truth_source"] = truth.kind
            row["right"] = row["truth"]["max_m"] <= RIGHT_M
            row["overlay"] = overlay(p, st, case, out, truth)
        rows.append(row)
    return rows


def _scan_label(stem: str) -> str:
    parts = stem.split("_")                 # ST_Name_id_year_scale_geo
    return f"{parts[-3]} ({parts[-4]})" if len(parts) >= 5 else stem


def _content(r: dict) -> str:
    note = r["editions"]
    if not note:
        return "–"
    if r["editions_agree"] is None:
        return "nothing to compare" + (" (no overlap)" if "covers" in note else " (no correlation)")
    shift = note.split("content shift ")[1].split(" m")[0]
    return ("agrees" if r["editions_agree"] else "**disagrees**") + f", shift {shift} m"


def _water(r: dict) -> str:
    note = r.get("basemap")
    if not note:
        return "–"
    if r["basemap_agree"] is None:
        return "nothing to compare"
    shift = note.split("shift ")[1].split(" m")[0]
    return ("agrees" if r["basemap_agree"] else "**disagrees**") + f", shift {shift} m"


def table(rows: list[dict]) -> str:
    out = ["| case | scan | nodes | residual at nodes | other scan, by content | water vs OSM | decision | vs USGS georeference (median / max) |",
           "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        tr = (f"{r['truth']['median_m']:.0f} / {r['truth']['max_m']:.0f} m" + ("" if r["right"] else " **wrong**")) if r.get("truth") else "–"
        res = f"{r['residual_m']:.1f} m" if r["residual_m"] is not None else "–"
        out.append(f"| {r['case']} | {_scan_label(r['scan'])} | {r['nodes']} | {res} | {_content(r)} | {_water(r)} | **{r['action']}** | {tr} |")
    return "\n".join(out)


def tally(rows: list[dict]) -> dict:
    t = {"accepted right": 0, "accepted wrong": 0, "review (right)": 0, "review (wrong)": 0, "abstain": 0}
    for r in rows:
        if r["action"] == "abstain":
            t["abstain"] += 1
        elif r["action"] == "accept":
            t["accepted right" if r["right"] else "accepted wrong"] += 1
        else:
            t["review (right)" if r["right"] else "review (wrong)"] += 1
    return t


DECISION_CODE = ("ga/primitives/graticule.py", "ga/primitives/basemap.py", "ga/primitives/generic.py", "ga/kinds.py", "ga/decide.py", "ga/guard.py", "ga/loop.py")


def provenance() -> dict:
    """Which code made these numbers: the commit, whether ga/ differed from it, and a hash of the decision code."""
    import subprocess
    def git(*args):
        try:
            return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=20).stdout.strip()
        except Exception:                                               # noqa: BLE001  not a checkout: say so
            return ""
    h = hashlib.sha256()
    for f in DECISION_CODE:
        h.update(f.encode()); h.update((ROOT / f).read_bytes())
    return {"commit": git("rev-parse", "--short", "HEAD") or "unknown", "ga_modified": bool(git("status", "--porcelain", "--", "ga")),
            "decision_code_sha256": h.hexdigest(), "library_version": kinds.SPECS[KIND].library_version}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cases", default=str(ROOT / "demo" / "cases.json"))
    ap.add_argument("--data", default=DEFAULT_DATA)
    ap.add_argument("--out", default=str(ROOT / "demo" / "out"))
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    spec = json.loads(Path(a.cases).read_text())
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    reg = kinds.registry_for(KIND)
    decider = Decider(kinds.policy_for(KIND), None, lambda st: st.hypotheses[0].score if st.hypotheses else None)
    rows, errors, t0 = [], [], time.time()
    for case in spec["cases"]:
        if a.only and case["id"] not in a.only:
            continue
        print(f"{case['id']}: {case['sheet']}", flush=True)
        try:
            case_rows = run_case(case, spec.get("base_url"), Path(a.data) if not spec.get("data_dir") or a.data != DEFAULT_DATA else ROOT / spec["data_dir"], out, reg, decider)
        except Exception as e:                                          # noqa: BLE001  one bad scan is a row, not the end of the run
            print(f"  ERROR {type(e).__name__}: {str(e)[:120]}", flush=True)
            errors.append({"case": case["id"], "error": f"{type(e).__name__}: {str(e)[:200]}"})
            continue
        for r in case_rows:
            rows.append(r)
            tr = f"{r['truth']['median_m']:.0f}/{r['truth']['max_m']:.0f} m from USGS" if r.get("truth") else "no placement"
            print(f"  {r['scan']:<40} {r['action']:<8} {tr}   {r['why'][:70]}", flush=True)
    real = [r for r in rows if not r["control"]]; ctrl = [r for r in rows if r["control"]]
    t = {"sheets": tally(real), "controls": tally(ctrl)}
    def line(name, x, n):
        return f"{name} ({n} scans): " + ", ".join(f"{k} {v}" for k, v in x.items())
    prov = provenance()
    md = (table(rows) + "\n\n" + line("sheets", t["sheets"], len(real)) + "  \n" + line("controls", t["controls"], len(ctrl))
          + f"  \n{len(rows)} scans in {time.time() - t0:.0f} s; {len(errors)} cases failed to run"
          + f"  \ncode {prov['commit']}{' (ga/ modified!)' if prov['ga_modified'] else ''}, decision code sha256 {prov['decision_code_sha256'][:12]}\n")
    (out / "results.md").write_text(md)
    (out / "results.json").write_text(json.dumps({"provenance": prov, "cases_file": a.cases, "tally": t, "errors": errors, "rows": rows}, indent=1))
    print("\n" + md)
    print(f"written: {out / 'results.md'}, {out / 'results.json'}, overlays in {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
