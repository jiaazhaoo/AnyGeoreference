"""Fill the OSM water cache for every sheet of some case files, two requests at a time (Overpass fair use).

    python benchmarks/prefetch_osm.py demo/cases.json benchmarks/usgs15_heldout_v3.json
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ga.primitives.basemap import osm_water, query_box   # noqa: E402

CRS = "EPSG:4267"            # the survey_graticule recipe places in the printed (NAD27) datum


def main() -> int:
    boxes = []
    for f in sys.argv[1:]:
        for c in json.loads(Path(f).read_text())["cases"]:
            for b in c.get("bounds_per_scan") or [c["bounds"]]:
                q = query_box(b, c["interval_min"], CRS)
                if q not in boxes:
                    boxes.append(q)
    def one(q):
        try:
            return len(osm_water(*q))
        except Exception as e:                                   # noqa: BLE001
            return f"failed: {e}"
    with ThreadPoolExecutor(2) as ex:
        for i, (q, n) in enumerate(zip(boxes, ex.map(one, boxes)), 1):
            print(f"{i}/{len(boxes)} {tuple(round(v, 3) for v in q)}: {n}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
