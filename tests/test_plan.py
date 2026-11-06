import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0, "/env/code/geo-eval")
from ga.knowledge import Index, load
from ga.plan import make_plan
from ga.orchestrate import profile_batch
from ga import Sheet


def test_knowledge_retrieval():
    idx = Index()
    assert len(idx.cards) >= 10
    top = [c.id for _, c in idx.retrieve("printed graticule corner coordinates polynomial residual", kind="historical_map", cues=["grid"], k=3)]
    assert top[0] in ("family-survey-graticule", "matcher-graticule-corners")
    top = [c.id for _, c in idx.retrieve("house numbers road names address register", kind="planning_drawing", cues=["number"], k=3)]
    assert "matcher-text-anchors" in top
    assert "family-survey-graticule" not in [c.id for _, c in idx.retrieve("anything", kind="planning_drawing", k=40)]   # kind filter


def test_plan_validation_and_truth_rank():
    sheets = [Sheet(f"s{i}", "historical_map", "x.tif", f"sha256:{i}", {"sheet_code": "053BSW"}, {"width": 10, "height": 10}) for i in range(3)]
    readings = [{"cues": [{"kind": "grid", "text": "76,30", "bbox": [0, 0, 1, 1]}], "north_arrow": "up"}] * 3
    prof = profile_batch(sheets, readings)
    assert prof["n_sheets"] == 3 and prof["cue_kinds_common"] == ["grid"]
    canned = {"recipe": [{"primitive": "graticule_frame"}, {"primitive": "control_point_fit", "params": {"model": "poly2"}}, {"primitive": "residual_check"},
                         {"primitive": "osm_reference"}, {"primitive": "structure_match"}, {"primitive": "hypothesis_agreement"}],
              "truth_sources": [{"kind": "batch_agreement", "how": "adjacent sheets share edges", "trust": 0.6}, {"kind": "self_consistency", "how": "node residual", "trust": 0.3}],
              "evaluation": {"metrics": ["placed_right"], "tolerance_m": 100, "split": "pilot on sheet 1"}, "stop_rules": {"accept_when": "residual and structure agree"},
              "missing_primitives": [], "risks": ["frame one line off"], "why": "graticule first"}
    plan, _ = make_plan(prof, "knowledge", 3, lambda s, u: canned)
    assert plan.problems() == [] and plan.best_truth() == "batch_agreement" and plan.can_accept()
    single, _ = make_plan(prof, "knowledge", 1, lambda s, u: canned)
    assert "batch agreement claimed for a single sheet" in single.problems()
    weak = dict(canned, truth_sources=[{"kind": "self_consistency", "how": "residual", "trust": 0.3}], recipe=[{"primitive": "graticule_frame"}, {"primitive": "made_up"}])
    p2, _ = make_plan(prof, "knowledge", 3, lambda s, u: weak)
    pr = p2.problems()
    assert any("made_up" in x for x in pr) and any("no matcher" in x for x in pr) and any("unverified" in x for x in pr) and not p2.can_accept()


def test_parse_json_answer_variants():
    from ga.claude_cli import parse_json_answer
    assert parse_json_answer('```json\n{"a": 1}\n```')["a"] == 1
    assert parse_json_answer('Here: {"a": {"b": 2}} done')["a"]["b"] == 2
    assert parse_json_answer('"{\\"a\\": 3}"')["a"] == 3


def test_unknown_params_are_reported_and_dropped():
    from ga.primitives import LIBRARY
    assert LIBRARY["control_point_fit"].unknown_params({"model": "affine", "bogus": 1}) == ["bogus"]
    t = LIBRARY["control_point_fit"].tool(model="affine", bogus=1)        # does not raise
    assert t.name == "control_point_fit"
