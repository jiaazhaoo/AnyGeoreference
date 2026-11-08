import math
import os
import sqlite3
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ga.loop import State
from ga.model import Candidate, Cue, Sheet
from ga.primitives.generated.toponym_constellation_fit import toponym_constellation_fit


# -- a ground-truth similarity: metric = scale * (R @ px) + t -------------------------------------------------------
THETA_DEG = 25.0
SCALE_M_PER_PX = 3.0
TX, TY = 400000.0, 300000.0


def _metric(px, py):
    th = math.radians(THETA_DEG)
    R = np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]])
    x, y = (SCALE_M_PER_PX * (R @ np.array([px, py])))
    return TX + x, TY + y


NAMES_PX = {
    "Fenmoor Reach": (100.0, 150.0),
    "Saltmarsh Rand": (300.0, 120.0),
    "Cockle Marsh": (220.0, 280.0),
    "Wyvern Ait": (80.0, 230.0),
    "Blackwater Hythe": (340.0, 200.0),
    "Thorney Carr": (150.0, 90.0),
}


def _make_db(path, names_metric, extra=()):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE open_names (NAME1 TEXT, TYPE TEXT, LOCAL_TYPE TEXT, GEOMETRY_X REAL, GEOMETRY_Y REAL)")
    for name, (x, y) in names_metric.items():
        con.execute("INSERT INTO open_names VALUES (?, 'other', 'Marsh', ?, ?)", (name, x, y))
    for name, x, y in extra:
        con.execute("INSERT INTO open_names VALUES (?, 'other', 'Marsh', ?, ?)", (name, x, y))
    con.commit()
    con.close()


def _state(names_px, db_path):
    sheet = Sheet("s1", "historical_map", "dummy.png", "sha256:" + "0" * 64, meta={"width": 500, "height": 400})
    cues = []
    for name, (px, py) in names_px.items():
        cues.append(Cue(sheet.digest, "place", name, (px - 5, py - 5, px + 5, py + 5), "test", 1.0))
    metrics = [_metric(*p) for p in names_px.values()]
    xs = [m[0] for m in metrics]; ys = [m[1] for m in metrics]
    r = 2000.0
    x0, y0, x1, y1 = min(xs) - r, min(ys) - r, max(xs) + r, max(ys) + r
    area = f"POLYGON(({x0} {y0},{x1} {y0},{x1} {y1},{x0} {y1},{x0} {y0}))"
    cand = Candidate(sheet.digest, "gazetteer", area, "EPSG:27700", tuple(names_px), 1.0, note="place_lookup test area")
    return State(sheet=sheet, cues=cues, candidates=[cand]), db_path


def test_accepts_a_consistent_constellation_and_recovers_the_transform():
    names_metric = {n: _metric(*p) for n, p in NAMES_PX.items()}
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "names.sqlite")
        _make_db(db_path, names_metric)
        state, db_path = _state(NAMES_PX, db_path)
        out = toponym_constellation_fit(state, db=db_path)

    assert len(out) == 1
    h = out[0]
    assert h.matcher == "toponym_constellation_fit"
    assert h.crs == "EPSG:27700"
    assert 0.0 < h.score <= 1.0

    a, b, c, dd, e, f = h.transform
    for name, (px, py) in NAMES_PX.items():
        pred = (a * px + b * py + c, dd * px + e * py + f)
        true = _metric(px, py)
        assert math.dist(pred, true) < 1.0, f"{name}: {pred} vs {true}"


def test_abstains_with_too_few_named_points():
    few = dict(list(NAMES_PX.items())[:3])          # below min_names
    names_metric = {n: _metric(*p) for n, p in few.items()}
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "names.sqlite")
        _make_db(db_path, names_metric)
        state, db_path = _state(few, db_path)
        out = toponym_constellation_fit(state, db=db_path)
    assert out == []


def test_abstains_when_gazetteer_has_no_matching_names():
    names_metric = {n: _metric(*p) for n, p in NAMES_PX.items()}
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "names.sqlite")
        _make_db(db_path, {})                        # empty gazetteer: nothing matches
        state, db_path = _state(NAMES_PX, db_path)
        out = toponym_constellation_fit(state, db=db_path)
    assert out == []
