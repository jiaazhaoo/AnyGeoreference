import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from ga.recipe import AdapterSpec, Pilot, Profile, Recipe, RecipeVersion, Step

LIB = {"colour_plates", "ocr_labels", "grid_reading", "gazetteer_search", "control_point_fit", "snap_faces"}


def _recipe():
    prof = Profile("1-inch survey sheet", ("sha256:a",), ("black", "brown", "blue"), ("place", "elevation"), printed_grid="corner-coordinates",
                   scale_hint="1:63360", era="1917-1933", measured_by={"colour_plates": "kmeans-lab", "printed_grid": "ocr-corners"})
    return Recipe("soi-1inch", "historical_map", prof, ("grid", "place"), ("gazetteer",), ("control_point_fit",), ("cross_edition",),
                  ({"id": "residual_ok", "when": "residual_m <= 15", "to": "accept"},), (5.0, 15.0), 0.02)


def test_spec_is_composition_only():
    r = _recipe()
    spec = AdapterSpec("sha256:r", (Step("grid_reading"), Step("control_point_fit", {"model": "affine"}), Step("invent_matcher")), r.policy_rules, "lib-v0")
    assert spec.validate(LIB) == ["invent_matcher"]


def test_no_truth_no_recipe():
    r = _recipe()
    spec = AdapterSpec("sha256:r", (Step("grid_reading"), Step("control_point_fit")), r.policy_rules, "lib-v0")
    bad = Pilot(("sha256:a",), "archive-published", {"placed_right": 3, "placed_wrong": 1}, gate_ok=False)
    with pytest.raises(ValueError):
        RecipeVersion(r, spec, bad, "v1")
    good = Pilot(("sha256:a",), "archive-published", {"placed_right": 4, "placed_wrong": 0}, gate_ok=True)
    v = RecipeVersion(r, spec, good, "v1")
    assert v.digest().startswith("sha256:") and v.digest() == RecipeVersion(r, spec, good, "v1").digest()
