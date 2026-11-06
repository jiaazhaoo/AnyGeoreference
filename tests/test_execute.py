import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0, "/env/code/geo-eval")
from ga.execute import generic_policy, registry_for_plan
from ga.plan import Plan
from ga.recipe import AdapterSpec, Step


def test_generic_policy_needs_a_second_family():
    p = generic_policy()
    assert p.decide({"best_score": 0.95, "residual_within_bound": True}).action == "review"      # self-consistency alone
    assert p.decide({"places_in_footprint": 2}).action == "accept"
    assert p.decide({"address_in_footprint": True}).action == "accept"
    assert p.decide({"overlay_agreement": 0.7, "residual_within_bound": True}).action == "accept"
    assert p.decide({"overlay_agreement": 0.7}).action == "review"


def test_registry_for_plan_skips_unknown_and_keeps_order():
    plan = Plan(AdapterSpec("t", (Step("control_point_fit", {"model": "affine", "bogus": 1}), Step("made_up", {}), Step("residual_check", {})), (), "lib"), [], {}, {})
    reg, skipped = registry_for_plan(plan)
    assert "control_point_fit" in reg and "residual_check" in reg and "made_up" not in reg
    assert skipped == ["made_up: not in the library"]
