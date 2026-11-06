import math
import os
import sqlite3
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, "/env/code/geo-eval")

from ga.loop import State
from ga.model import Candidate, Cue, Hypothesis, Sheet
from ga.primitives.generated.thin_plate_spline_warp import thin_plate_spline_warp


# -- a hand sketch: drawn roughly to scale (a similarity captures the gist) but each label is nudged, the way a
# tourist map or a letter's sketch puts names near their junctions without being metrically honest. -----------------
THETA_DEG = 10.0
SCALE_M_PER_PX = 5.0
TX, TY = 450000.0, 210000.0


def _metric(px, py):
    th = math.radians(THETA_DEG)
    R = np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]])
    x, y = SCALE_M_PER_PX * (R @ np.array([px, py]))
    return TX + x, TY + y


NAMES_PX = {
    "Fenmoor Reach": (100.0, 150.0),
    "Saltmarsh Rand": (300.0, 120.0),
    "Cockle Marsh": (220.0, 280.0),
    "Wyvern Ait": (80.0, 230.0),
    "Blackwater Hythe": (340.0, 200.0),
}

# each name's TRUE gazetteer position is the similarity-metric position plus a sketch-sized wobble: the similarity
# fit will show a real (but modest) residual, which is exactly the distortion score this primitive must report.
WOBBLE_M = {
    "Fenmoor Reach": (15.0, -10.0),
    "Saltmarsh Rand": (-12.0, 8.0),
    "Cockle Marsh": (9.0, 12.0),
    "Wyvern Ait": (-8.0, -14.0),
    "Blackwater Hythe": (6.0, -6.0),
}


def _make_db(path, names_metric):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE open_names (NAME1 TEXT, TYPE TEXT, LOCAL_TYPE TEXT, GEOMETRY_X REAL, GEOMETRY_Y REAL)")
    for name, (x, y) in names_metric.items():
        con.execute("INSERT INTO open_names VALUES (?, 'other', 'Marsh', ?, ?)", (name, x, y))
    con.commit()
    con.close()


def _state(names_px, hypothesis_coeffs):
    sheet = Sheet("s1", "historical_map", "dummy.png", "sha256:" + "0" * 64, meta={"width": 500, "height": 400})
    cues = [Cue(sheet.digest, "place", name, (px - 5, py - 5, px + 5, py + 5), "test", 1.0)
            for name, (px, py) in names_px.items()]
    metrics = [_metric(*p) for p in names_px.values()]
    xs = [m[0] for m in metrics]; ys = [m[1] for m in metrics]
    r = 2000.0
    x0, y0, x1, y1 = min(xs) - r, min(ys) - r, max(xs) + r, max(ys) + r
    area = f"POLYGON(({x0} {y0},{x1} {y0},{x1} {y1},{x0} {y1},{x0} {y0}))"
    cand = Candidate(sheet.digest, "gazetteer", area, "EPSG:27700", tuple(names_px), 1.0, note="place_lookup test area")
    a, b, c, d, e, f = hypothesis_coeffs
    h = Hypothesis(sheet.digest, hypothesis_coeffs, "POLYGON EMPTY", "EPSG:27700", 0.8, "toponym_constellation_fit",
                   (0,), note="similarity; rms 12.0 m")
    return State(sheet=sheet, cues=cues, candidates=[cand], hypotheses=[h])


def _similarity_coeffs():
    th = math.radians(THETA_DEG)
    a = SCALE_M_PER_PX * math.cos(th); b = -SCALE_M_PER_PX * math.sin(th)
    d = SCALE_M_PER_PX * math.sin(th); e = SCALE_M_PER_PX * math.cos(th)
    return (a, b, TX, d, e, TY)


def _wobbled_metric():
    out = {}
    for name, px_py in NAMES_PX.items():
        gx, gy = _metric(*px_py)
        wx, wy = WOBBLE_M[name]
        out[name] = (gx + wx, gy + wy)
    return out


def test_warps_label_positions_onto_their_wobbled_gazetteer_hits_within_tolerance():
    names_metric = _wobbled_metric()
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "names.sqlite")
        _make_db(db_path, names_metric)
        state = _state(NAMES_PX, _similarity_coeffs())
        out = thin_plate_spline_warp(state, db=db_path)

    assert len(out) == 1                      # no real raster on disk -> points layer only
    layer = out[0]
    assert layer.kind == "points"
    assert layer.name == "tps_warped_labels"
    assert layer.frame == "EPSG:27700"
    assert layer.meta["tag"] == "schematic, not for measurement"
    assert layer.meta["n_control_points"] == len(NAMES_PX)
    assert layer.meta["distortion_score_m"] > 0.0          # the wobble is real, the similarity fit must see it

    by_name = {p["name"]: p for p in layer.data}
    assert len(by_name) == len(NAMES_PX)
    for name, (px, py) in NAMES_PX.items():
        wx, wy = by_name[name]["warped_xy"]
        tx, ty = names_metric[name]
        # TPS interpolates EXACTLY at its own control points: the warp must land each label on its true position.
        assert math.dist((wx, wy), (tx, ty)) < 1e-6, f"{name}: {(wx, wy)} vs {(tx, ty)}"


def test_abstains_below_min_control_points():
    few = dict(list(NAMES_PX.items())[:2])     # below min_control = 3
    names_metric = {n: _metric(*p) for n, p in few.items()}
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "names.sqlite")
        _make_db(db_path, names_metric)
        state = _state(few, _similarity_coeffs())
        out = thin_plate_spline_warp(state, db=db_path)
    assert out == []


def test_abstains_without_a_hypothesis_or_candidate():
    sheet = Sheet("s1", "historical_map", "dummy.png", "sha256:" + "1" * 64, meta={"width": 500, "height": 400})
    state = State(sheet=sheet)
    assert thin_plate_spline_warp(state) == []
