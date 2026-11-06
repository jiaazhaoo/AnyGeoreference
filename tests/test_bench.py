import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0, "/env/code/geo-eval")
from ga import Hypothesis, Verdict, ABSTAIN
from ga.bench import TruthCase, score, actions_of, labels_for_gate


def _v(case, wkt, p=0.9):
    h = Hypothesis("d", (1, 0, 0, 0, 1, 0), wkt, "EPSG:27700", 0.8, "m") if wkt else None
    return Verdict("d", h, p if h else None, "accept" if h else ABSTAIN, "", (), 0.01, 1.0)


def test_score_and_gate_view():
    truth = {"a": TruthCase("a", "POLYGON((0 0,10 0,10 10,0 10,0 0))", "EPSG:27700", 20),
             "b": TruthCase("b", "POLYGON((0 0,10 0,10 10,0 10,0 0))", "EPSG:27700", 20),
             "c": TruthCase("c", "POLYGON((0 0,10 0,10 10,0 10,0 0))", "EPSG:27700", 20)}
    verdicts = {"a": _v("a", "POLYGON((2 2,12 2,12 12,2 12,2 2))"), "b": _v("b", "POLYGON((500 500,510 500,510 510,500 510,500 500))"), "c": _v("c", None)}
    s = score(verdicts, truth)
    assert s["placed_right"]["k"] == 1 and s["placed_wrong"]["k"] == 1 and s["abstained"]["k"] == 1
    assert actions_of(verdicts) == {"a": "accept", "b": "accept", "c": "review"}
    assert labels_for_gate(s) == {"a": "right", "b": "wrong", "c": "right"}
