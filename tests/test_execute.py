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


def test_missing_required_params_skip_instead_of_raising():
    from ga.primitives import LIBRARY
    from ga.loop import State, step
    from ga.tools.registry import ToolRegistry
    from ga import Sheet
    t = LIBRARY["graticule_frame_bounds"].tool()           # west/south/east/north not given
    st = State(Sheet("s", "historical_map", "x.tif", "sha256:0", {}, {"width": 10, "height": 10}))
    reg = ToolRegistry().add(t)
    rec = step(st, reg, "graticule_frame_bounds")
    assert rec["produced"] == 0 and st.evidence[0].name == "graticule_frame_bounds_missing_params"


def test_loop_survives_a_raising_tool():
    from ga.loop import State, step
    from ga.tools.registry import Tool, ToolRegistry
    from ga import Sheet
    def boom(state):
        raise ImportError("No module named 'paddleocr'")
    reg = ToolRegistry().add(Tool("boom", (), "cue", "sheet-reader", True, 0.0, boom, "raises"))
    st = State(Sheet("s", "k", "x.tif", "sha256:0", {}, {}))
    rec = step(st, reg, "boom")
    assert rec["error"].startswith("ImportError") and st.trace[-1] is rec


def test_revise_parsing_is_tolerant():
    from ga.plan import Plan, revise_plan
    from ga.recipe import AdapterSpec
    base = Plan(AdapterSpec("t", (), (), "lib"), [], {}, {})
    new, _ = revise_plan(base, [], lambda s, u: {"action": "revise", "recipe": ["claude_read", {"name": "place_lookup"}, {"tool": "toponym_constellation_fit", "params": {"min_consistent_triples": 3}}], "missing_primitives": ["x_y"]})
    assert [s.primitive for s in new.recipe.steps] == ["claude_read", "place_lookup", "toponym_constellation_fit"] and new.missing_primitives == [{"name": "x_y"}]
    none, _ = revise_plan(base, [], lambda s, u: {"action": "revise", "recipe": [{"params": {}}]})
    assert none is None


def test_a_runaway_tool_is_stopped_by_its_deadline():
    import os, time
    from ga.loop import State, step
    from ga.tools.registry import Tool, ToolRegistry
    from ga import Sheet
    def spin(state):
        while True:
            time.sleep(0.05)
    os.environ["GA_TOOL_TIMEOUT"] = "1"
    try:
        reg = ToolRegistry().add(Tool("spin", (), "cue", "geometry", True, 0.0, spin, "never ends"))
        st = State(Sheet("s", "k", "x.tif", "sha256:0", {}, {}))
        t0 = time.time(); rec = step(st, reg, "spin")
        assert time.time() - t0 < 3 and "ran past 1 s" in rec["error"]
    finally:
        os.environ.pop("GA_TOOL_TIMEOUT")


def test_planner_params_are_cast_or_dropped():
    from ga.primitives import LIBRARY, coerce_params
    impl = LIBRARY["road_name_fit"].impl
    kept, dropped = coerce_params(impl, {"search_m": "2000", "theta_step": 5, "inlier_m": "0.02-5"})
    assert kept == {"search_m": 2000.0, "theta_step": 5.0} and dropped and "inlier_m" in dropped[0]
