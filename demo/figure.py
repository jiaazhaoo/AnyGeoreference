"""The README figure from a demo run: one accepted sheet and the caught misread, side by side.

    python demo/run_demo.py && python demo/figure.py
"""
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "demo" / "out"
PANELS = [("boston_bay__MA_Boston_Bay_352517_1903_62500_geo.jpg", "Boston Bay 1903: graticule lines", "accepted; 17 m median from USGS"),
          ("duluth__MN_Duluth_504380_1953_62500_geo.jpg", "Duluth 1953: ticks and crosses", "placed 11 m from USGS (the old reader: 26 km)")]


def panel(img, title, sub, h=900):
    img = cv2.resize(img, (int(img.shape[1] * h / img.shape[0]), h), interpolation=cv2.INTER_AREA)
    bar = np.full((70, img.shape[1], 3), 255, np.uint8)
    cv2.putText(bar, title, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (20, 20, 20), 2, cv2.LINE_AA)
    cv2.putText(bar, sub, (12, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (60, 60, 60), 1, cv2.LINE_AA)
    return np.vstack([bar, img])


def main() -> int:
    ps = [panel(cv2.imread(str(OUT / f)), t, s) for f, t, s in PANELS]
    gap = np.full((ps[0].shape[0], 20, 3), 255, np.uint8)
    row = np.hstack([ps[0], gap, ps[1]])
    leg = np.full((40, row.shape[1], 3), 255, np.uint8)
    cv2.drawMarker(leg, (20, 20), (0, 0, 220), cv2.MARKER_CROSS, 16, 2)
    cv2.putText(leg, "nodes the loop read", (36, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (40, 40, 40), 1, cv2.LINE_AA)
    cv2.circle(leg, (260, 20), 8, (200, 90, 0), 2)
    cv2.putText(leg, "where USGS's own georeference puts them (the truth, never read by the loop)", (276, 26),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (40, 40, 40), 1, cv2.LINE_AA)
    dst = ROOT / "docs" / "img" / "demo_usgs.jpg"
    dst.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(dst), np.vstack([row, leg]), [cv2.IMWRITE_JPEG_QUALITY, 82])
    print(dst)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
