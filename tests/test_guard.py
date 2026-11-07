import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0, "/env/code/geo-eval")
from evalcore import Evidence
from ga import Sheet
from ga.loop import State
from ga.model import Hypothesis

WKT = "POLYGON((600000 300000,601000 300000,601000 301000,600000 301000,600000 300000))"


def _st():
    return State(Sheet("s", "k", "x", "sha256:s", {}, {"width": 1000, "height": 1000}))


def test_every_matcher_is_refused_a_mirrored_placement():
    st = _st()
    n = st.add("hypothesis", [Hypothesis("sha256:s", (1.0, 0, 600000, 0, 1.0, 300000), WKT, "EPSG:27700", 0.9, "any_generated_matcher")])
    assert n == 0 and st.evidence[-1].name == "hypothesis_rejected" and "mirrors" in st.evidence[-1].value
    st.evidence.append(Evidence("sheet_mirrored", True, "deterministic", "sheet-reader"))
    assert st.add("hypothesis", [Hypothesis("sha256:s", (1.0, 0, 600000, 0, 1.0, 300000), WKT, "EPSG:27700", 0.9, "m")]) == 1


def test_degenerate_fits_are_refused():
    st = _st()
    bad = [Hypothesis("sha256:s", (1.0, 0, 0, 0, -0.1, 0), WKT, "EPSG:27700", 0.9, "m"),          # axes 10x apart
           Hypothesis("sha256:s", (1e-6, 0, 0, 0, -1e-6, 0), WKT, "EPSG:27700", 0.9, "m")]        # a micrometre per pixel
    assert st.add("hypothesis", bad) == 0 and len([e for e in st.evidence if e.name == "hypothesis_rejected"]) == 2
    geo = Hypothesis("sha256:s", (1.6243e-5, 0, 0.0, 0, -1e-5, 52.0), "POLYGON((0 52,0.01 52,0.01 51.99,0 51.99,0 52))", "EPSG:4326", 0.9, "m")
    assert st.add("hypothesis", [geo]) == 1                                        # degrees: axis ratio measured in metres


def test_a_check_on_the_matchers_own_reference_is_not_a_second_family():
    from ga.decide import Decider
    from ga.execute import generic_policy
    st = _st()
    st.add("hypothesis", [Hypothesis("sha256:s", (1.0, 0, 600000, 0, -1.0, 301000), WKT, "EPSG:27700", 0.9, "toponym_constellation_fit")])
    st.evidence.append(Evidence("places_in_footprint", 5, "deterministic", "gazetteer"))
    d = Decider(generic_policy(), None, lambda s: 0.9)
    f = d.facts(st)
    assert f["places_in_footprint"] is None and f["not_independent"]
    assert d.decide(st).action == "review"
    st2 = _st()
    st2.add("hypothesis", [Hypothesis("sha256:s", (1.0, 0, 600000, 0, -1.0, 301000), WKT, "EPSG:27700", 0.9, "road_name_fit")])
    st2.evidence.append(Evidence("places_in_footprint", 5, "deterministic", "gazetteer"))
    assert d.decide(st2).action == "accept"                                        # road network vs gazetteer: independent


def test_thresholds_are_library_owned_sheet_facts_are_not():
    from ga.primitives import LIBRARY
    kept, dropped = LIBRARY["graticule_frame_bounds"].plan_params({"west": -1.0, "south": 50.0, "east": 0.0, "north": 51.0, "interval_min": 2.5})
    assert kept["interval_min"] == 2.5 and not dropped
    kept, dropped = LIBRARY["road_name_fit"].plan_params({"min_inliers": 8, "search_m": 2000})
    assert kept == {} and len(dropped) == 2


def test_two_readings_merge_into_a_union_with_confirmation(tmp_path):
    import json
    from ga.primitives.claude_reader import merged_reading
    (tmp_path / "s.json").write_text(json.dumps({"cues": [{"kind": "place", "text": "Erith", "bbox": [0, 0, 1, 1]}], "north_arrow": "up"}))
    (tmp_path / "s.r2.json").write_text(json.dumps({"cues": [{"kind": "place", "text": "ERITH", "bbox": [0, 0, 1, 1]},
                                                             {"kind": "grid", "text": "51 30' N", "bbox": [0, 5, 1, 6], "confidence": 0.9}]}))
    m = merged_reading("s", tmp_path)
    by = {c["text"]: c for c in m["cues"]}
    assert m["n_readings"] == 2 and by["Erith"]["confirmed"] and not by["51 30' N"]["confirmed"] and by["51 30' N"]["confidence"] == 0.5
    assert m["north_arrow"] == "up" and m["confirmed_share"] == 0.5
