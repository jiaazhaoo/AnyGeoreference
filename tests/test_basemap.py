"""The external water check on a synthetic coloured sheet; the OSM reference is replaced by the sheet's own rivers moved to WGS84."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cv2
import numpy as np
from pyproj import Transformer

from ga.primitives import basemap
from ga.primitives.generic import fit_transform

BOUNDS = (-71.0, 42.25, -70.75, 42.5)
STEP = 5 / 60
W, H = 3000, 3800
PAPER, BLUE = (250, 244, 214), (120, 170, 205)


def _rivers(seed=3, n=14):
    """Rivers as lon/lat polylines over the sheet and a little beyond (the printed datum)."""
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        p = np.array([rng.uniform(-71.03, -70.72), rng.uniform(42.22, 42.53)])
        pts = [p]
        for _ in range(40):
            p = p + rng.normal(0, 0.004, 2)
            pts.append(p)
        out.append(np.array(pts))
    return out


def _sheet(rivers, colour=True):
    """px -> lon/lat linear over the sheet; rivers drawn in blue on yellowed paper (grey ink if colour is False)."""
    img = np.full((H, W, 3), PAPER, np.uint8)
    for r in rivers:
        px = np.c_[(r[:, 0] - BOUNDS[0]) / (BOUNDS[2] - BOUNDS[0]) * W, (BOUNDS[3] - r[:, 1]) / (BOUNDS[3] - BOUNDS[1]) * H]
        cv2.polylines(img, [px.round().astype(np.int32)], False, BLUE if colour else (110, 110, 110), 4)
    gx, gy = np.meshgrid(np.linspace(0, W, 5), np.linspace(0, H, 5))
    px = np.c_[gx.ravel(), gy.ravel()]
    ll = np.c_[BOUNDS[0] + px[:, 0] / W * (BOUNDS[2] - BOUNDS[0]), BOUNDS[3] - px[:, 1] / H * (BOUNDS[3] - BOUNDS[1])]
    return img, ll, px


def _osm(rivers, monkeypatch):
    to_wgs = Transformer.from_crs("EPSG:4267", "EPSG:4326", always_xy=True)
    lines = [np.c_[to_wgs.transform(r[:, 0], r[:, 1])] for r in rivers]
    monkeypatch.setattr(basemap, "osm_reference", lambda *a, **k: ([], lines, "test rivers"))


def test_right_placement_agrees_with_osm_water(monkeypatch):
    rivers = _rivers(); _osm(rivers, monkeypatch)
    img, ll, px = _sheet(rivers)
    c, _ = fit_transform(px, ll, "poly2")
    r = basemap.basemap_shift(img, c, "poly2", "EPSG:4267", BOUNDS, 5.0)
    assert "why" not in r and math.hypot(r["dx_m"], r["dy_m"]) < 60 and r["response"] > 0.05


def test_a_record_one_interval_off_shows_as_that_shift(monkeypatch):
    rivers = _rivers(); _osm(rivers, monkeypatch)
    img, ll, px = _sheet(rivers)
    wrong = ll - np.array([STEP, 0.0])                       # the record's bounds 5' too far west: every label moves
    c, _ = fit_transform(px, wrong, "poly2")
    shifted = (BOUNDS[0] - STEP, BOUNDS[1], BOUNDS[2] - STEP, BOUNDS[3])
    r = basemap.basemap_shift(img, c, "poly2", "EPSG:4267", shifted, 5.0)
    k = 111320 * math.cos(math.radians(42.375)) * STEP
    assert abs(abs(r["dx_m"]) - k) < 150 and abs(r["dy_m"]) < 150 and r["response"] > 0.05


def test_a_grey_scan_has_no_water_and_compares_nothing(monkeypatch):
    rivers = _rivers(); _osm(rivers, monkeypatch)
    img, ll, px = _sheet(rivers, colour=False)
    c, _ = fit_transform(px, ll, "poly2")
    assert "why" in basemap.basemap_shift(img, c, "poly2", "EPSG:4267", BOUNDS, 5.0)


def test_policy_lets_an_external_disagreement_outrank_agreeing_editions():
    from ga import kinds
    pol = kinds.policy_for("survey_graticule")
    assert pol.decide({"residual_within_bound": True, "basemap_agree": True}).action == "accept"
    assert pol.decide({"residual_within_bound": True, "editions_agree": True, "basemap_agree": False}).action == "review"
    assert pol.decide({"residual_within_bound": True, "editions_agree": True}).action == "accept"


def test_tile_polygons_are_filled_so_tile_seams_leave_no_edge(monkeypatch):
    """A lake cut in two by a tile edge arrives as two polygons; filled together, the seam is not an outline."""
    img = np.full((H, W, 3), PAPER, np.uint8)
    lake = np.array([[-70.97, 42.47], [-70.78, 42.47], [-70.80, 42.31], [-70.95, 42.28]])
    px = np.c_[(lake[:, 0] - BOUNDS[0]) / (BOUNDS[2] - BOUNDS[0]) * W, (BOUNDS[3] - lake[:, 1]) / (BOUNDS[3] - BOUNDS[1]) * H]
    cv2.fillPoly(img, [px.round().astype(np.int32)], BLUE)
    to_wgs = Transformer.from_crs("EPSG:4267", "EPSG:4326", always_xy=True)
    w = lambda a: np.c_[to_wgs.transform(a[:, 0], a[:, 1])]
    cut = -70.875                                            # a tile edge through the lake
    left = np.array([[-70.97, 42.47], [cut, 42.47], [cut, 42.2958], [-70.95, 42.28]])
    right = np.array([[cut, 42.47], [-70.78, 42.47], [-70.80, 42.31], [cut, 42.2958]])
    monkeypatch.setattr(basemap, "osm_reference", lambda *a, **k: ([[w(left)], [w(right)]], [], "test tiles"))
    gx, gy = np.meshgrid(np.linspace(0, W, 5), np.linspace(0, H, 5))
    p = np.c_[gx.ravel(), gy.ravel()]
    ll = np.c_[BOUNDS[0] + p[:, 0] / W * (BOUNDS[2] - BOUNDS[0]), BOUNDS[3] - p[:, 1] / H * (BOUNDS[3] - BOUNDS[1])]
    c, _ = fit_transform(p, ll, "poly2")
    r = basemap.basemap_shift(img, c, "poly2", "EPSG:4267", BOUNDS, 5.0)
    assert "why" not in r and math.hypot(r["dx_m"], r["dy_m"]) < 60


def test_a_partner_shown_wrong_takes_an_agreeing_scan_to_review():
    from ga import kinds
    pol = kinds.policy_for("survey_graticule")
    f = {"residual_within_bound": True, "editions_agree": True}
    assert pol.decide({**f, "partner_basemap_agree": False}).action == "review"
    assert pol.decide({**f, "partner_basemap_agree": True}).action == "accept"
