import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, "/env/code/geo-eval")

from ga.loop import State
from ga.model import Cue, Hypothesis, Sheet
from ga.primitives.generated.neighbour_sheet_tiling import neighbour_sheet_tiling

# -- two synthetic 1884-style sheets, A (the current sheet) and B (its neighbour to the right) ---------------------
# A: sheet px -> CRS is the identity (a=1,b=0,c=0,d=0,e=1,f=0); its right margin is at px x=1000 -> CRS x=1000.
A_TRANSFORM = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
A_W, A_H = 1000.0, 600.0
# B: sheet px -> CRS shifts by (1000, 0); its left margin (px x=0) lands on the same CRS seam, x=1000, when the
# two sheets tile correctly.
B_W, B_H = 1000.0, 600.0


def _sheet(transform=A_TRANSFORM, w=A_W, h=A_H, extra_meta=None):
    meta = {"width": w, "height": h}
    if extra_meta:
        meta.update(extra_meta)
    sheet = Sheet("a", "historical_map", "a.tif", "sha256:" + "a" * 64, meta=meta)
    hyp = Hypothesis(sheet.digest, transform, "POLYGON EMPTY", "EPSG:27700", 0.9, "test")
    return sheet, hyp


def _road_cue(sheet_digest, name, x, y):
    return Cue(sheet_digest, "road", name, (x - 5, y - 5, x + 5, y + 5), "test", 1.0)


def _neighbour(transform, w, h, roads, side="left"):
    return {"side": side, "width": w, "height": h, "transform": transform, "roads": roads}


def _b_roads(name, y, dx=(10.0, 90.0)):
    return {"name": name, "points": [[dx[0], y], [dx[1], y]]}


def test_accepts_roads_that_continue_across_a_well_tiled_seam():
    sheet, hyp = _sheet()
    cues = [
        _road_cue(sheet.digest, "High Street", 920, 200), _road_cue(sheet.digest, "High Street", 980, 200),
        _road_cue(sheet.digest, "Church Road", 910, 400), _road_cue(sheet.digest, "Church Road", 990, 400),
    ]
    b_transform = (1.0, 0.0, 1000.0, 0.0, 1.0, 0.0)          # B's px -> CRS: seam lands on A's seam exactly
    roads = [_b_roads("High St", 200), _b_roads("Church Rd", 400)]
    sheet.meta["neighbour"] = _neighbour(b_transform, B_W, B_H, roads, side="right")

    state = State(sheet=sheet, cues=cues, hypotheses=[hyp])
    out = neighbour_sheet_tiling(state)

    by_name = {e.name: e for e in out}
    assert by_name["neighbour_tiling_roads_matched"].value == 2
    assert by_name["neighbour_tiling_mean_offset_m"].value < 1.0
    assert by_name["neighbour_tiling_accepted"].value is True
    for e in out:
        assert e.family == "road-network" and e.source == "deterministic"


def test_rejects_a_seam_with_a_real_gap_and_jump():
    sheet, hyp = _sheet()
    cues = [
        _road_cue(sheet.digest, "High Street", 920, 200), _road_cue(sheet.digest, "High Street", 980, 200),
        _road_cue(sheet.digest, "Church Road", 910, 400), _road_cue(sheet.digest, "Church Road", 990, 400),
    ]
    # B is mis-fitted: its seam is 150 m further out and 30 m along-seam from A's -- a bad tiling, not noise.
    b_transform = (1.0, 0.0, 1150.0, 0.0, 1.0, 30.0)
    roads = [_b_roads("High St", 200), _b_roads("Church Rd", 400)]
    sheet.meta["neighbour"] = _neighbour(b_transform, B_W, B_H, roads, side="right")

    state = State(sheet=sheet, cues=cues, hypotheses=[hyp])
    out = neighbour_sheet_tiling(state)

    by_name = {e.name: e for e in out}
    assert by_name["neighbour_tiling_roads_matched"].value == 2
    assert by_name["neighbour_tiling_mean_offset_m"].value > 100.0
    assert by_name["neighbour_tiling_accepted"].value is False


def test_abstains_with_fewer_than_two_continuing_roads():
    sheet, hyp = _sheet()
    cues = [
        _road_cue(sheet.digest, "High Street", 920, 200), _road_cue(sheet.digest, "High Street", 980, 200),
        _road_cue(sheet.digest, "Mill Lane", 910, 400), _road_cue(sheet.digest, "Mill Lane", 990, 400),
    ]
    b_transform = (1.0, 0.0, 1000.0, 0.0, 1.0, 0.0)
    roads = [_b_roads("High St", 200), _b_roads("Totally Different Avenue", 400)]   # only one name matches
    sheet.meta["neighbour"] = _neighbour(b_transform, B_W, B_H, roads, side="right")

    state = State(sheet=sheet, cues=cues, hypotheses=[hyp])
    out = neighbour_sheet_tiling(state)

    by_name = {e.name: e for e in out}
    assert by_name["neighbour_tiling_roads_matched"].value == 1
    assert by_name["neighbour_tiling_accepted"].value is False


def test_returns_nothing_without_a_neighbour_or_a_hypothesis():
    sheet, hyp = _sheet()
    cues = [_road_cue(sheet.digest, "High Street", 920, 200)]

    state_no_neighbour = State(sheet=sheet, cues=cues, hypotheses=[hyp])
    assert neighbour_sheet_tiling(state_no_neighbour) == []

    sheet2, hyp2 = _sheet()
    sheet2.meta["neighbour"] = _neighbour((1.0, 0.0, 1000.0, 0.0, 1.0, 0.0), B_W, B_H,
                                          [_b_roads("High St", 200)], side="right")
    state_no_hypothesis = State(sheet=sheet2, cues=cues, hypotheses=[])
    assert neighbour_sheet_tiling(state_no_hypothesis) == []
