import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pytest
from evalcore import Evidence
from ga import kinds
from ga import Cue, FixedPlan, Hypothesis, Layer, Sheet, State, run
from ga.primitives import LIBRARY, generic, table


def test_library_and_three_kinds_validate():
    assert len(LIBRARY) >= 20
    for k in ("plans_gb", "soi_1inch", "unlabelled_raster", "street_map", "survey_graticule"):
        assert kinds.validate(k) == [], k
    assert "declared" in table()                      # some primitives are declared-only on purpose
    assert set(kinds.KINDS) == {"plans_gb", "soi_1inch", "unlabelled_raster", "street_map", "survey_graticule"}


def test_control_point_fit_recovers_affine():
    rng = np.random.default_rng(0)
    A = np.array([[0.5, 0.02, 400000.0], [-0.01, -0.5, 300000.0]])     # pixels -> BNG, y flipped
    px = rng.uniform(0, 3000, (12, 2))
    xy = (A[:, :2] @ px.T).T + A[:, 2] + rng.normal(0, 0.05, (12, 2))
    sheet = Sheet("g", "historical_map", "none.png", "sha256:g", meta={"width": 3000, "height": 3000})
    st = State(sheet)
    st.cues = [Cue("sha256:g", "grid", f"{x},{y}", (p[0] - 1, p[1] - 1, p[0] + 1, p[1] + 1), "t") for p, (x, y) in zip(px, xy)]
    hs = generic.control_point_fit(st, model="affine", crs="EPSG:27700")
    assert len(hs) == 1 and np.allclose(hs[0].transform, (A[0, 0], A[0, 1], A[0, 2], A[1, 0], A[1, 1], A[1, 2]), atol=1e-2)
    st.hypotheses = hs
    ev = generic.residual_check(st, bound=0.5)
    assert ev[0].value < 0.3 and ev[1].value is True
    assert generic.control_point_fit(State(sheet), model="poly2") == []    # no cues -> nothing, never a guess


def test_each_kind_runs_with_stubs():
    """The loop runs for all three kinds with stub implementations for anything not bound on this machine."""
    def hyp(state):
        return [Hypothesis(state.sheet.digest, (1, 0, 0, 0, -1, 0), "POLYGON((0 0,1 0,1 1,0 1,0 0))", "EPSG:27700", 0.7, "stub", ())]
    def cues(state):
        return [Cue(state.sheet.digest, "grid", f"{i*10},{i*10}", (i, i, i + 1, i + 1), "stub") for i in range(8)]
    def layer(name, kind):
        return lambda state: [Layer(state.sheet.digest, name, kind, np.zeros((10, 10), np.uint8))]
    stubs = {n: hyp for n in ("structure_match", "structure_match_orb", "text_anchor_fit", "grid_figures", "plan_minima_match")}
    stubs.update({"ocr_words": cues, "ocr_cached": cues, "claude_read": cues, "address_in_footprint": lambda s: [], "edge_structure": layer("edges", "mask"), "reference_render": layer("reference_render", "mask"), "overlay_agreement": lambda s: [], "graticule_frame": cues, "road_and_place_labels": lambda s: [], "graticule_frame": cues,
                  "gazetteer_search": lambda s: [], "snap_faces": lambda s: [Evidence("snap_iou", 0.9, "deterministic", "geometry")],
                  "plate_separation": layer("black", "mask"), "line_structure": layer("line_structure", "polylines"),
                  "osm_reference": lambda s: [], "cross_edition_agreement": lambda s: [], "sheet_index_lookup": lambda s: [],
                  "edge_structure": layer("edges", "mask"), "reference_render": layer("reference_render", "mask"),
                  "overlay_agreement": lambda s: [Evidence("overlay_agreement", 0.7, "deterministic", "basemap")],
                  "hint_area": lambda s: [], "place_lookup": lambda s: [], "road_junction_locate": lambda s: [], "road_name_fit": hyp, "places_in_footprint": lambda s: []})
    for k in ("plans_gb", "soi_1inch", "unlabelled_raster", "street_map"):
        reg = kinds.registry_for(k, stubs)
        sheet = Sheet("s", kinds.KINDS[k].kind, "none.png", "sha256:s", meta={"width": 100, "height": 100})
        st = run(sheet, reg, FixedPlan(kinds.plan_for(k)))
        assert st.trace, k
        if k == "unlabelled_raster":
            # no hint -> no candidate -> reference_render skipped -> nothing to match: the loop ends with no hypothesis
            assert not st.candidates and any(t.get("skipped") for t in st.trace)
        else:
            assert st.hypotheses, k


def test_unavailable_is_explicit():
    from ga.primitives import LIBRARY, Primitive, register
    register(Primitive("declared_only_demo", "geometry", True, (), "evidence", "declared, no implementation", None, "generic"))
    from ga.recipe import AdapterSpec, Step
    kinds.SPECS["demo_kind"] = AdapterSpec("demo_kind", (Step("declared_only_demo"),), (), "lib-v0")
    assert kinds.unavailable("demo_kind") == ["declared_only_demo"]     # never silently skipped
    with pytest.raises(RuntimeError):
        kinds.registry_for("demo_kind")
    del kinds.SPECS["demo_kind"]; del LIBRARY["declared_only_demo"]


def test_cross_edition_agreement():
    from ga.primitives.soi import cross_edition_agreement
    sheet = Sheet("e", "historical_map", "x.tif", "sha256:e", {"sheet_code": "053ASE"},
                  {"sibling_id": "053ASE_1925", "sibling_footprint_wkt": "POLYGON((76 30.5,76.5 30.5,76.5 30,76 30,76 30.5))"})
    st = State(sheet)
    st.hypotheses = [Hypothesis("sha256:e", (1, 0, 0, 0, -1, 0), "POLYGON((76.0003 30.5,76.5003 30.5,76.5003 30,76.0003 30,76.0003 30.5))", "EPSG:4326", 0.9, "control_point_fit")]
    ev = {e.name: e for e in cross_edition_agreement(st, tol_m=100)}
    assert ev["editions_agree"].value is True and 25 < ev["editions_distance_m"].value < 35      # 0.0003 deg lon ~ 29 m
    st.hypotheses = [Hypothesis("sha256:e", (1, 0, 0, 0, -1, 0), "POLYGON((76.01 30.5,76.51 30.5,76.51 30,76.01 30,76.01 30.5))", "EPSG:4326", 0.9, "control_point_fit")]
    assert {e.name: e.value for e in cross_edition_agreement(st)}["editions_agree"] is False
