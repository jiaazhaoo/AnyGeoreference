import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from evalcore import Calibrator, Evidence, Policy, Rule
from ga import ABSTAIN, Candidate, Cue, Decider, FixedPlan, Hypothesis, Planner, Sheet, State, Tool, ToolRegistry, run

SHEET = Sheet("S1", "plans_gb", "s1.png", "sha256:abc", {"address": "1 High Street"})


def registry():
    r = ToolRegistry()
    r.add(Tool("read_sheet", (), "cue", "sheet-reader", False, 0.01,
               lambda s: [Cue(s.sheet.digest, "road", "HIGH STREET", (0, 0, 10, 2), "read_sheet", 0.9),
                          Cue(s.sheet.digest, "number", "1", (3, 3, 4, 4), "read_sheet", 0.8)], "VLM reads road names and numbers"))
    r.add(Tool("gazetteer", ("cue",), "candidate", "gazetteer", True, 0.0,
               lambda s: [Candidate(s.sheet.digest, "gazetteer", "POLYGON((0 0,1 0,1 1,0 1,0 0))", "EPSG:27700",
                                    tuple(c.text for c in s.cues if c.kind == "road"), 0.7)], "road names -> areas"))
    r.add(Tool("text_anchor_fit", ("cue", "candidate"), "hypothesis", "geometry", True, 0.0,
               lambda s: [Hypothesis(s.sheet.digest, (1, 0, 0, 0, -1, 0), "POLYGON((0 0,1 0,1 1,0 1,0 0))", "EPSG:27700", 0.8, "text_anchor_fit", (0,)),
                          Hypothesis(s.sheet.digest, (1, 0, 5, 0, -1, 5), "POLYGON((5 5,6 5,6 6,5 6,5 5))", "EPSG:27700", 0.3, "text_anchor_fit", (0,))], "fit cues to candidates"))
    r.add(Tool("snap_faces", ("hypothesis",), "evidence", "geometry", True, 0.0,
               lambda s: [Evidence("snap_iou", 0.9, "deterministic", "geometry"),
                          Evidence("address_inside", True, "deterministic", "address-register")], "best hypothesis vs map faces"))
    return r


def test_invariants():
    with pytest.raises(ValueError):
        Cue("d", "latitude", "x", (0, 0, 1, 1), "r")
    with pytest.raises(ValueError):
        Hypothesis("d", (1, 0, 0), "POLYGON EMPTY", "EPSG:27700", 0.5, "m")
    with pytest.raises(ValueError):
        Tool("t", (), "cue", "model", True, 0.0, lambda s: [])


def test_fixed_plan_and_decide(tmp_path):
    r = registry()
    state = run(SHEET, r, FixedPlan(["gazetteer", "read_sheet", "gazetteer", "text_anchor_fit", "snap_faces"]), tmp_path / "trace.jsonl")
    assert state.trace[0]["skipped"]                                  # gazetteer before cues: recorded, not run
    assert len(state.hypotheses) == 2 and state.hypotheses[0].score == 0.8   # sorted best first
    assert abs(state.cost - 0.01) < 1e-9                              # only the model call costs
    pol = Policy("ga-demo", "v0", [Rule("snap_and_address", lambda f: f["snap_iou"] >= 0.86 and f["address_inside"], "accept",
                                        when_text="snaps to faces and the address is inside")])
    cal = Calibrator.fit([0.2, 0.5, 0.8, 0.9], [False, False, True, True])
    d = Decider(pol, cal, lambda s: s.hypotheses[0].score, min_probability=0.6)
    v = d.decide(state)
    assert v.action == "accept" and v.placement is state.hypotheses[0] and v.probability >= 0.6
    assert "snap_and_address" in v.trail and (tmp_path / "trace.jsonl").exists()
    empty = State(SHEET)
    assert d.decide(empty).action == ABSTAIN
    strict = Decider(pol, cal, lambda s: 0.2, min_probability=0.6)
    assert strict.decide(state).action == ABSTAIN                     # low probability -> abstain, even though a rule accepted


def test_planner_sees_no_coordinates_and_is_bounded():
    r = registry()
    seen = []
    def choose(summary, options):
        seen.append(summary)
        names = [o["name"] for o in options]
        for want in ("read_sheet", "gazetteer", "text_anchor_fit", "snap_faces"):
            if want in names and want not in summary["steps"]:
                return want
        return "stop"
    state = run(SHEET, r, Planner(choose, max_steps=10, max_cost=0.5))
    assert [t["tool"] for t in state.trace if t["tool"] != "planner"] == ["read_sheet", "gazetteer", "text_anchor_fit", "snap_faces"]
    import json
    assert "POLYGON" not in json.dumps(seen) and "transform" not in json.dumps(seen)
    capped = run(SHEET, r, Planner(choose, max_steps=10, max_cost=0.005))
    assert any(t.get("stopped") == "cost cap" for t in capped.trace) and not capped.cues


def test_step_session_roundtrip(tmp_path):
    from ga.session import StepSession
    r = registry()
    ses = StepSession.start(tmp_path / "s", SHEET, "plans_gb")
    o = ses.options(r)
    assert "read_sheet" in [x["name"] for x in o["options"]] and "gazetteer" not in [x["name"] for x in o["options"]]
    ses.choose(r, "read_sheet", "cues first", chooser="test")
    ses.choose(r, "gazetteer", "names -> areas", chooser="test")
    st = ses.load()
    assert st.cues and st.candidates and [t["chose"] for t in st.trace if t["tool"] == "planner"] == ["read_sheet", "gazetteer"]
    assert (tmp_path / "s" / "choices.jsonl").exists()
