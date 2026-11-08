"""Marks count beyond chance; a sheet that prints only its neatline is placed by the frame's corners, in the record's
datum, and accepted only on an external reference."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cv2
import numpy as np

from ga import FixedPlan, Sheet, kinds, run
from ga.guard import _geographic
from ga.primitives.generic import apply_transform
from ga.primitives.graticule import _fit_of, read_frame_marks
from test_graticule import BOUNDS, _ticks_sheet

PLACE = ["graticule_marks", "control_point_fit"]


def _place(img, tmp_path, record):
    p = tmp_path / "s.png"; cv2.imwrite(str(p), img)
    sheet = Sheet("s", "historical_map", str(p), "sha256:s", {"bounds": list(BOUNDS), "interval_min": 5, **record},
                  {"width": img.shape[1], "height": img.shape[0]})
    return run(sheet, kinds.registry_for("survey_graticule"), FixedPlan(PLACE))


def _ev(st, name):
    return next((e.value for e in st.evidence if e.name == name), None)


def test_printed_marks_stand_above_the_chance_rate():
    img, _ = _ticks_sheet(grid=False)
    g = read_frame_marks(img, *BOUNDS, interval_min=5.0)
    assert g["found"] and g["marks"] >= 0.9 and g["chance_marks"] < 0.5


def test_a_neatline_without_marks_is_placed_by_its_corners_in_the_record_datum(tmp_path):
    img, truth = _ticks_sheet(grid=False, marks=False)
    st = _place(img, tmp_path, {"datum": "EPSG:4314"})
    assert _ev(st, "graticule_found") is False and _ev(st, "graticule_frame_only") is True
    assert len(st.cues) == 4 and st.hypotheses
    h = st.hypotheses[0]
    assert h.crs == "EPSG:4314" and h.note.startswith("affine")
    coeffs, model = _fit_of(h)
    px = np.array([[x, y] for x, y, _, _ in truth]); ll = np.array([[lo, la] for _, _, lo, la in truth])
    err = np.abs(apply_transform(coeffs, px, model) - ll) * np.array([111320 * math.cos(math.radians(42.4)), 110574])
    assert err.max() < 30                                         # metres, over every node of the sheet


def test_a_frame_only_placement_needs_the_external_reference():
    pol = kinds.policy_for("survey_graticule")
    f = {"residual_within_bound": True, "graticule_frame_only": True}
    assert pol.decide({**f, "editions_agree": True}).action == "review"
    assert pol.decide({**f, "basemap_agree": True}).action == "accept"
    assert pol.decide({**f, "editions_agree": True, "basemap_agree": True}).action == "accept"
    assert pol.decide({"residual_within_bound": True, "editions_agree": True, "graticule_frame_only": False}).action == "accept"


def test_any_geographic_datum_is_degrees_to_the_guard():
    assert _geographic("EPSG:4314") and _geographic("EPSG:4267") and not _geographic("EPSG:31468")
