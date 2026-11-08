"""The series field: learned from other sheets' external checks, never from the sheet itself; refused where nearby
sheets share no error; applied to the record; and never a reason to accept."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np

from ga import kinds
from ga.series import Anchor, SeriesField, correct, offset_at


def _grid(field, noise=20.0, seed=0, outliers=()):
    """Sheets on a 10' x 6' grid over 2 x 1.2 degrees; each anchor = the field there + measurement noise."""
    rng = np.random.default_rng(seed)
    out = []
    for i in range(12):
        for j in range(12):
            lon, lat = 12.0 + i / 6, 50.2 + j / 10
            dx, dy = field(lon, lat)
            if (i, j) in outliers:
                dx, dy = dx + 700, dy - 500                     # a river that moved: one sheet's water says nonsense
            out.append(Anchor(f"c{i}_{j}", lon, lat, dx + rng.normal(0, noise), dy + rng.normal(0, noise)))
    return out


def _saxon_like(lon, lat):
    return -390.0 * (lon - 13.5), 80.0 * (lat - 50.8)


def test_the_field_predicts_a_sheet_it_never_saw():
    A = _grid(_saxon_like, outliers=((3, 4), (8, 8)))
    f = SeriesField(A).predict(13.0, 50.75, exclude="c6_5")
    assert f is not None and "c6_5" not in str(f)
    dx, dy = offset_at(f, 13.0, 50.75)
    tx, ty = _saxon_like(13.0, 50.75)
    assert abs(dx - tx) < 30 and abs(dy - ty) < 30 and f["loo_m"] < 60


def test_the_sheet_itself_is_left_out():
    A = _grid(_saxon_like, noise=0.0)
    me = next(a for a in A if a.key == "c6_5")
    A = [a if a.key != "c6_5" else Anchor(a.key, a.lon, a.lat, a.dx_m + 5000, a.dy_m) for a in A]   # its own water, wildly off
    f = SeriesField(A).predict(me.lon, me.lat, exclude="c6_5")
    dx, _ = offset_at(f, me.lon, me.lat)
    assert abs(dx - _saxon_like(me.lon, me.lat)[0]) < 20          # not pulled by its own measurement


def test_no_shared_error_no_field():
    rng = np.random.default_rng(1)
    A = [Anchor(f"k{i}", 12 + rng.uniform(0, 2), 50.2 + rng.uniform(0, 1.2), rng.normal(0, 300), rng.normal(0, 300)) for i in range(120)]
    assert SeriesField(A).predict(13.0, 50.8, exclude="k0") is None


def test_too_far_from_any_anchor_no_field():
    assert SeriesField(_grid(_saxon_like)).predict(8.0, 48.0) is None


def test_correction_moves_the_record_by_the_field():
    f = SeriesField(_grid(_saxon_like, noise=0.0)).predict(12.5, 50.5)
    lon, lat = correct(f, 12.5, 50.5)
    dx, dy = _saxon_like(12.5, 50.5)
    assert abs((lon - 12.5) * 111320 * np.cos(np.radians(50.5)) - dx) < 5 and abs((lat - 50.5) * 110574 - dy) < 5


def test_a_series_corrected_placement_is_never_accepted():
    pol = kinds.policy_for("survey_graticule")
    f = {"residual_within_bound": True, "series_corrected": True}
    assert pol.decide({**f, "basemap_agree": True}).action == "review"
    assert pol.decide({**f, "editions_agree": True, "basemap_agree": True}).action == "review"
