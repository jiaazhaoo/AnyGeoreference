"""The generic graticule reader and the edition check, on synthetic sheets (no downloads, no reference data)."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cv2
import numpy as np

from ga import FixedPlan, Sheet, kinds, run
from ga.primitives.generic import fit_transform
from ga.primitives.graticule import _fit_of, content_shift, read_graticule

BOUNDS = (-71.0, 42.25, -70.75, 42.5)          # a 15' sheet, 5' graticule: 4 x 4 nodes
STEP = 5 / 60


def _scene(seed: int = 0, size: int = 1600) -> np.ndarray:
    """Map content in a metric frame: random roads (polylines) and lakes, dark on white."""
    rng = np.random.default_rng(seed)
    img = np.full((size, size), 255, np.uint8)
    for _ in range(60):
        pts = np.cumsum(rng.normal(0, 40, (8, 2)), axis=0) + rng.uniform(0, size, 2)
        cv2.polylines(img, [pts.astype(np.int32)], False, 40, 2)
    for _ in range(25):
        cv2.circle(img, tuple(int(v) for v in rng.uniform(0, size, 2)), int(rng.uniform(8, 50)), 90, -1)
    return img


def _sheet_image(offset=(300, 260), spacing=(1300.0, None), scene_seed=0, lines=True):
    """A scan: collar, map content, and (optionally) a graticule of hairlines with the paper spacing ratio."""
    lat0 = (BOUNDS[1] + BOUNDS[3]) / 2
    dx = spacing[0]
    dy = spacing[1] or dx / math.cos(math.radians(lat0))
    W, H = int(2 * offset[0] + 3 * dx), int(2 * offset[1] + 3 * dy)
    img = np.full((H, W), 245, np.uint8)
    scene = cv2.resize(_scene(scene_seed), (int(3 * dx), int(3 * dy)))
    img[offset[1]:offset[1] + scene.shape[0], offset[0]:offset[0] + scene.shape[1]] = scene
    nodes = []
    for j in range(4):
        for i in range(4):
            nodes.append((offset[0] + i * dx, offset[1] + j * dy, BOUNDS[0] + i * STEP, BOUNDS[3] - j * STEP))
    if lines:
        for i in range(4):
            x = int(round(offset[0] + i * dx)); cv2.line(img, (x, offset[1]), (x, int(offset[1] + 3 * dy)), 0, 2)
        for j in range(4):
            y = int(round(offset[1] + j * dy)); cv2.line(img, (offset[0], y), (int(offset[0] + 3 * dx), y), 0, 2)
    return img, nodes


def test_reader_finds_every_node_of_a_clean_graticule():
    img, truth = _sheet_image()
    g = read_graticule(img, *BOUNDS, interval_min=5.0)
    assert g["found"] and len(g["nodes"]) == 16 and g["pixel_space"] == "paper"
    err = [math.hypot(x - tx, y - ty) for (x, y, lo, la), (tx, ty, tlo, tla) in zip(g["nodes"], truth)]
    assert max(err) < 2.0
    assert all(abs(lo - tlo) < 1e-9 and abs(la - tla) < 1e-9 for (_, _, lo, la), (_, _, tlo, tla) in zip(g["nodes"], truth))


def test_reader_finds_nothing_without_lines_and_the_loop_abstains(tmp_path):
    img, _ = _sheet_image(lines=False)
    assert read_graticule(img, *BOUNDS, interval_min=5.0)["found"] is False
    p = tmp_path / "nolines.png"; cv2.imwrite(str(p), img)
    sheet = Sheet("n", "historical_map", str(p), "sha256:n", {"bounds": list(BOUNDS), "interval_min": 5}, {"width": img.shape[1], "height": img.shape[0]})
    st = run(sheet, kinds.registry_for("survey_graticule"), FixedPlan(kinds.plan_for("survey_graticule")))
    assert not st.cues and not st.hypotheses
    assert any(e.name == "graticule_found" and e.value is False for e in st.evidence)


def _fit(nodes, model="poly2"):
    c, _ = fit_transform(np.array([(x, y) for x, y, _, _ in nodes]), np.array([(lo, la) for _, _, lo, la in nodes]), model)
    return c, model


def test_content_shift_is_zero_for_two_right_placements_and_an_interval_for_a_misread():
    a, na = _sheet_image(offset=(300, 260), spacing=(1300.0, None))
    b, nb = _sheet_image(offset=(180, 340), spacing=(1240.0, None))        # another scan: other collar, other resolution
    fa, fb = _fit(na), _fit(nb)
    dx, dy, resp, overlap = content_shift(a, fa, b, fb, BOUNDS, 5.0)
    assert overlap > 0.9 and math.hypot(dx, dy) < 40
    c, m = fa
    off = c.copy(); off[0, 0] += STEP                                      # scan a read one meridian off
    dx, dy, resp, _ = content_shift(a, (off, m), b, fb, BOUNDS, 5.0)
    k = 111320 * math.cos(math.radians(42.375)) * STEP
    assert abs(abs(dx) - k) < 100 and abs(dy) < 100 and resp > 0.05         # disagrees by exactly one interval


def test_survey_graticule_policy_needs_the_second_family():
    pol = kinds.policy_for("survey_graticule")
    assert pol.decide({"residual_within_bound": True}).action == "review"
    assert pol.decide({"residual_within_bound": True, "editions_agree": True}).action == "accept"
    assert pol.decide({"residual_within_bound": True, "editions_agree": False}).action == "review"
    assert pol.decide({"residual_within_bound": True, "editions_agree": True, "graticule_ambiguous": True}).action == "review"


def test_fit_note_round_trips():
    img, nodes = _sheet_image()
    from ga import Cue, State
    from ga.primitives.generic import control_point_fit
    st = State(Sheet("r", "historical_map", "x.png", "sha256:r", meta={"width": img.shape[1], "height": img.shape[0]}))
    st.cues = [Cue("sha256:r", "grid", f"{lo},{la}", (x - 1, y - 1, x + 1, y + 1), "t") for x, y, lo, la in nodes]
    h = control_point_fit(st, model="poly2", crs="EPSG:4267")[0]
    c, m = _fit_of(h)
    assert m == "poly2" and c.shape == (6, 2)


def _ticks_sheet(seed=1, dx=1300.0, offset=(320, 300), grid=True):
    """A 1950s-style sheet: neatline, one-sided edge ticks, interior crosses, no graticule lines; optionally a
    section-like square grid ruled across the map and through the neatline (the Duluth trap)."""
    lat0 = (BOUNDS[1] + BOUNDS[3]) / 2
    dy = dx / math.cos(math.radians(lat0))
    W, H = int(2 * offset[0] + 3 * dx), int(2 * offset[1] + 3 * dy)
    img = np.full((H, W), 248, np.uint8)
    x0, y0, x1, y1 = offset[0], offset[1], int(offset[0] + 3 * dx), int(offset[1] + 3 * dy)
    scene = cv2.resize(_scene(seed), (x1 - x0, y1 - y0))
    img[y0:y1, x0:x1] = np.minimum(scene, 185)                       # map content: tinted, stops at the neatline
    if grid:                                                          # square "sections", 1/5 of an interval, through the frame
        s = dx / 5
        for k in range(-3, 40):
            x = int(x0 + 0.37 * s + k * s); y = int(y0 + 0.61 * s + k * s)
            if x0 - 60 < x < x1 + 60:
                cv2.line(img, (x, y0 - 60), (x, y1 + 60), 30, 2)
            if y0 - 60 < y < y1 + 60:
                cv2.line(img, (x0 - 60, y), (x1 + 60, y), 30, 2)
    cv2.rectangle(img, (x0, y0), (x1, y1), 0, 2)
    nodes = []
    for j in range(4):
        for i in range(4):
            x, y = x0 + i * dx, y0 + j * dy
            nodes.append((x, y, BOUNDS[0] + i * STEP, BOUNDS[3] - j * STEP))
            X, Y = int(round(x)), int(round(y))
            if j == 0 and 0 < i < 3: cv2.line(img, (X, Y), (X, Y + 26), 0, 2)
            if j == 3 and 0 < i < 3: cv2.line(img, (X, Y - 26), (X, Y), 0, 2)
            if i == 0 and 0 < j < 3: cv2.line(img, (X, Y), (X + 26, Y), 0, 2)
            if i == 3 and 0 < j < 3: cv2.line(img, (X - 26, Y), (X, Y), 0, 2)
            if 0 < i < 3 and 0 < j < 3:
                cv2.line(img, (X - 20, Y), (X + 20, Y), 0, 2); cv2.line(img, (X, Y - 20), (X, Y + 20), 0, 2)
    return img, nodes


def test_marks_reader_places_a_ticks_and_crosses_sheet_through_a_ruled_grid():
    from ga.primitives.graticule import read_frame_marks
    img, truth = _ticks_sheet()
    g = read_frame_marks(img, *BOUNDS, interval_min=5.0)
    assert g["found"] and g["pixel_space"] == "paper"
    t = {(round(lo, 6), round(la, 6)): (x, y) for x, y, lo, la in truth}
    errs = [math.hypot(x - t[(round(lo, 6), round(la, 6))][0], y - t[(round(lo, 6), round(la, 6))][1]) for x, y, lo, la in g["nodes"]]
    assert len(g["nodes"]) >= 12 and max(errs) < 4.0


def test_marks_reader_finds_no_frame_on_a_bare_grid():
    from ga.primitives.graticule import read_frame_marks
    img = np.full((5200, 4200), 248, np.uint8)
    for k in range(0, 4200, 260):
        cv2.line(img, (k, 0), (k, 5199), 30, 2)
    for k in range(0, 5200, 260):
        cv2.line(img, (0, k), (4199, k), 30, 2)
    g = read_frame_marks(img, *BOUNDS, interval_min=5.0)
    assert not g["found"] or (len(g["nodes"]) - 4) / g["n_expected_marks"] < 0.5 or g["contrast"] <= 0.05


def test_a_rival_frame_is_ruled_out_only_by_evidence_that_separates_frames():
    from ga.primitives.graticule import ruled_out
    neatline = {"contrast": 0.15, "marks": 1.0}
    subgrid = {"contrast": 0.02, "marks": 1.0}           # section lines can carry every mark; content runs on past them
    assert ruled_out(neatline, subgrid)
    assert not ruled_out({"contrast": 0.03, "marks": 0.83}, {"contrast": 0.04, "marks": 0.75})   # neither stops the content
    assert not ruled_out({"contrast": 0.15, "marks": 0.75}, {"contrast": 0.02, "marks": 1.0})    # better content, fewer marks
