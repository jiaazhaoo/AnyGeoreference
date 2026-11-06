import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0, "/env/code/geo-eval")
from ga import kinds
from ga.compose import compare, compose


def test_compose_with_a_replayed_answer():
    canned = {"steps": [{"primitive": "graticule_frame"}, {"primitive": "control_point_fit", "params": {"model": "poly2"}},
                        {"primitive": "residual_check"}, {"primitive": "made_up_tool"}], "why": "grid first"}
    spec, _ = compose(kinds.SOI_1INCH.profile, lambda messages: canned)
    r = compare(spec, kinds.SPECS["soi_1inch"])
    assert r["invalid"] == ["made_up_tool"] and r["shared"] == 3 and r["has_verification"] and r["has_matcher"]
    assert r["order_agreement"] == 1.0 and "structure_match" in r["missing"]
