#!/usr/bin/env python3
"""cases.jsonl for the plans_gb experiments from a frozen benchmark council folder (crop as the sheet, cached OCR,
the client's graded polygon as truth). Data paths stay outside the repository."""
import json, os, sys
from pathlib import Path
sys.path.insert(0, os.environ.get("E2E_REPO", "/env/code/e2e-plan-extract"))
from PIL import Image
from e2e_plan_extract.s4_verify.qa_input_polygon import load_input

B, out, n, town_xy, town = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]), json.loads(sys.argv[4]), sys.argv[5]
plans = json.load(open(B / "lab/plans.json")); truth = load_input(B / "truth.gpkg")
seen, rows = set(), []
for p in plans:
    c = p["case"]
    if c in seen or len(rows) >= n:
        continue
    seen.add(c)
    stageA = str(B / "out/stageA" / c)
    ocr = f"{stageA}/ocr_top3.jsonl"
    if not os.path.exists(ocr):
        continue
    page_path = next((json.loads(l)["image_path"] for l in open(ocr) if json.loads(l)["image"] == p["page"]), None)
    yolo = json.load(open(f"{stageA}/yolo_plans.json"))
    top = next((t for t in yolo.get("top3", []) if t["output"].endswith(os.path.basename(p["image"]))), None)
    tp = truth.get(c, {}).get("geom")
    if not page_path or not os.path.exists(page_path) or not top or tp is None or tp.is_empty:
        continue
    crop = f"{stageA}/cropped-plan/{top['output']}"
    W, H = Image.open(crop).size; PW, PH = Image.open(page_path).size
    rows.append({"id": c, "image": crop, "record": {"address": p.get("address", ""), "proposal": p.get("proposal", "")},
                 "meta": {"width": W, "height": H, "page_size": [PW, PH], "crop_box": top["box"], "ocr_jsonl": ocr, "page": p["page"],
                          "town_xy": town_xy, "town": town},
                 "truth_wkt": tp.wkt, "crs": "EPSG:27700", "tolerance_m": 50})
with open(out, "w") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")
print(len(rows), "cases ->", out)
