import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shapely.geometry import LineString

from ga.loop import State
from ga.model import Hypothesis, Layer, Sheet
from ga.primitives.generated.polyline_shape_match import polyline_shape_match

# -- a sinuous reference shoreline in a metric CRS (EPSG:27700-like easting/northing), with real bends ------------
REF_LINE = LineString([
    (400000.0, 300000.0), (400300.0, 300400.0), (400700.0, 300250.0),
    (401000.0, 300700.0), (401400.0, 300550.0), (401800.0, 300900.0),
])

# ground-truth sheet px -> CRS: rotation + scale + translation, as the 6 Hypothesis coefficients
THETA = np.radians(12.0)
SCALE = 2.0
TX, TY = 399000.0, 299500.0
R = np.array([[np.cos(THETA), -np.sin(THETA)], [np.sin(THETA), np.cos(THETA)]])


def _to_crs(px):
    return (SCALE * (R @ np.asarray(px))) + np.array([TX, TY])


def _transform6():
    a = SCALE * R[0, 0]; b = SCALE * R[0, 1]
    d = SCALE * R[1, 0]; e = SCALE * R[1, 1]
    return (a, b, TX, d, e, TY)


def _to_px(crs_xy):
    """Inverse of _to_crs, for building sheet pixels that trace the reference line under the ground truth."""
    M = SCALE * R
    Minv = np.linalg.inv(M)
    return Minv @ (np.asarray(crs_xy) - np.array([TX, TY]))


def _sheet(name="s1"):
    return Sheet(name, "historical_map", "dummy.png", "sha256:" + "0" * 64, meta={"width": 2000, "height": 2000})


def _good_hypothesis(sheet):
    return Hypothesis(sheet.digest, _transform6(), "POLYGON EMPTY", "EPSG:27700", 0.8, "test_matcher")


def _offset_hypothesis(sheet, dx=5000.0, dy=5000.0):
    a, b, c, d, e, f = _transform6()
    return Hypothesis(sheet.digest, (a, b, c + dx, d, e, f + dy), "POLYGON EMPTY", "EPSG:27700", 0.8, "test_matcher")


def _traced_sheet_layer(sheet, ref_line=REF_LINE, n=400, noise_m=2.0, extra_outlier_px=None, seed=0):
    """A 'line_structure' polylines layer: points along the reference line, mapped back to sheet px by the
    ground-truth transform, with a little positional noise -- standing in for a traced/skeletonised coastline."""
    rng = np.random.default_rng(seed)
    coords = np.asarray(ref_line.coords, float)
    t = np.linspace(0, len(coords) - 1.001, n)
    idx = t.astype(int)
    frac = (t - idx)[:, None]
    pts_crs = coords[idx] * (1 - frac) + coords[idx + 1] * frac
    pts_crs += rng.normal(scale=noise_m, size=pts_crs.shape)
    pts_px = np.array([_to_px(p) for p in pts_crs])
    if extra_outlier_px is not None:
        pts_px = np.concatenate([pts_px, extra_outlier_px], axis=0)
    return Layer(sheet.digest, "line_structure", "polylines", [pts_px])


def _reference_layer(sheet, geoms=(REF_LINE,)):
    return Layer(sheet.digest, "reference_vectors", "vectors", list(geoms), frame="EPSG:27700")


def test_abstains_without_a_hypothesis_or_reference_layer():
    sheet = _sheet()
    state = State(sheet=sheet, layers=[_traced_sheet_layer(sheet)])
    assert polyline_shape_match(state) == []           # no hypothesis yet

    state2 = State(sheet=sheet, hypotheses=[_good_hypothesis(sheet)])
    assert polyline_shape_match(state2) == []           # no linework layer

    state3 = State(sheet=sheet, hypotheses=[_good_hypothesis(sheet)], layers=[_traced_sheet_layer(sheet)])
    assert polyline_shape_match(state3) == []           # no reference layer


def test_good_hypothesis_scores_a_high_matched_fraction_with_margin():
    sheet = _sheet()
    state = State(sheet=sheet, hypotheses=[_good_hypothesis(sheet)],
                  layers=[_traced_sheet_layer(sheet), _reference_layer(sheet)])
    out = polyline_shape_match(state)
    by_name = {e.name: e for e in out}

    assert by_name["polyline_shape_matched_fraction"].value > 0.9
    assert by_name["polyline_shape_chamfer_mean_m"].value < 25.0
    assert by_name["polyline_shape_chance_margin_ok"].value is True
    assert by_name["polyline_shape_has_curvature"].value is True
    for e in out:
        assert e.family == "geometry"
        assert e.source == "deterministic"


def test_wrong_hypothesis_scores_a_low_matched_fraction_and_fails_the_margin():
    sheet = _sheet()
    state = State(sheet=sheet, hypotheses=[_offset_hypothesis(sheet)],
                  layers=[_traced_sheet_layer(sheet), _reference_layer(sheet)])
    out = polyline_shape_match(state)
    by_name = {e.name: e for e in out}

    assert by_name["polyline_shape_matched_fraction"].value < 0.2
    assert by_name["polyline_shape_chance_margin_ok"].value is False


def test_outlier_stretch_is_clipped_rather_than_counted_against_the_match():
    sheet = _sheet()
    # a reclaimed stretch: a cluster of traced points far from the reference line, in CRS terms
    outlier_crs = np.array([[410000.0 + i * 50.0, 310000.0] for i in range(40)])
    outlier_px = np.array([_to_px(p) for p in outlier_crs])
    layer = _traced_sheet_layer(sheet, extra_outlier_px=outlier_px)
    state = State(sheet=sheet, hypotheses=[_good_hypothesis(sheet)], layers=[layer, _reference_layer(sheet)])
    out = polyline_shape_match(state)
    by_name = {e.name: e for e in out}

    # the matched fraction stays high despite ~10% of points being a reclaimed stretch nowhere near the shoreline
    assert by_name["polyline_shape_matched_fraction"].value > 0.85
    assert "outlier" in by_name["polyline_shape_matched_fraction"].note


def test_straight_reference_line_fails_the_curvature_guard():
    sheet = _sheet()
    straight = LineString([(400000.0, 300000.0), (402000.0, 300000.0)])
    layer = _traced_sheet_layer(sheet, ref_line=straight)
    state = State(sheet=sheet, hypotheses=[_good_hypothesis(sheet)],
                  layers=[layer, _reference_layer(sheet, geoms=(straight,))])
    out = polyline_shape_match(state)
    by_name = {e.name: e for e in out}
    assert by_name["polyline_shape_has_curvature"].value is False
