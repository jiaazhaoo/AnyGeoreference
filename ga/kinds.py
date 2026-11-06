"""The three kinds supported today, as recipes over the primitive library. A kind is data: which cues, which
references, which matchers, which verifications, which policy rules, in which order. `registry_for(kind)` turns
the recipe into a ToolRegistry; `validate()` proves composition-only against the library."""
from __future__ import annotations

from ga.primitives import LIBRARY, names
from ga.recipe import AdapterSpec, Profile, Recipe, Step
from ga.tools.registry import ToolRegistry

PLANS_GB = Recipe(
    name="plans_gb", kind="planning_drawing",
    profile=Profile("UK planning application drawing (site / location plan)", (), ("black", "red"), ("road", "number", "place", "grid"),
                    printed_grid="national-grid", scale_hint="1:1250 / 1:2500", era="1948-", measured_by={"text_kinds": "OCR + label rules"}),
    cues=("road", "number", "grid", "place"),
    references=("gazetteer", "address-register", "road-network", "basemap"),
    matchers=("text_anchor_fit", "grid_figures", "structure_match_orb"),
    verifications=("address_in_footprint", "overlay_agreement", "snap_faces", "hypothesis_agreement"),
    policy_rules=(
        {"id": "snap_and_address", "when": "snap_iou >= 0.86 and address_inside", "to": "accept"},
        {"id": "two_matchers_agree", "when": "matchers_agree", "to": "accept"},
        {"id": "far_from_record", "when": "record_distance_m > 2000", "from": "accept", "to": "review"},
    ),
    expected_accuracy_m=(2.0, 10.0), expected_cost_per_sheet=0.012,
    note="truth: the client's verdict on delivered polygons; abstain when neither snap nor address agrees")

SOI_1INCH = Recipe(
    name="soi_1inch", kind="historical_map",
    profile=Profile("Survey of India 1-inch / quarter-inch sheet, 1910s-40s", (), ("black", "red", "blue", "green", "yellow"),
                    ("place", "elevation", "gothic"), printed_grid="graticule", scale_hint="1:63360", era="1910-1945",
                    measured_by={"colour_plates": "plates.separate", "printed_grid": "frame.detect"}),
    cues=("grid", "place"),
    references=("basemap",),
    matchers=("control_point_fit", "structure_match"),
    verifications=("residual_check", "cross_edition_agreement", "overlay_agreement"),
    policy_rules=(
        {"id": "residual_ok", "when": "residual_within_bound", "to": "accept"},
        {"id": "editions_disagree", "when": "editions_agree == False", "from": "accept", "to": "review"},
    ),
    expected_accuracy_m=(5.0, 30.0), expected_cost_per_sheet=0.0,
    note="truth: the archive's published georeferencing and the printed graticule; 9 m residual on the pilot sheet")

UNLABELLED_RASTER = Recipe(
    name="unlabelled_raster", kind="raster_no_text",
    profile=Profile("aerial / satellite tile or map extract without readable text", (), (), (), printed_grid="none",
                    measured_by={"text_kinds": "OCR finds nothing usable"}),
    cues=(),
    references=("record-text", "basemap"),
    matchers=("structure_match_orb",),
    verifications=("overlay_agreement", "hypothesis_agreement"),
    policy_rules=(
        {"id": "overlay_strong", "when": "overlay_agreement >= 0.6", "to": "accept"},
        {"id": "no_candidate_area", "when": "n_candidates == 0", "to": "abstain"},
    ),
    expected_accuracy_m=(5.0, 50.0), expected_cost_per_sheet=0.0,
    note="no text: only structure; a candidate area must come from the record or a hint, else abstain")

KINDS = {r.name: r for r in (PLANS_GB, SOI_1INCH, UNLABELLED_RASTER)}

# the ordered composition each kind runs (the FixedPlan); the Planner picks from the same names
SPECS = {
    "plans_gb": AdapterSpec("plans_gb", (Step("ocr_cached"), Step("road_and_place_labels"), Step("gazetteer_search"), Step("grid_figures"),
                                        Step("text_anchor_fit"), Step("edge_structure"), Step("reference_render", {"res_m": 1.0}),
                                        Step("structure_match_orb", {"min_inliers": 10}), Step("overlay_agreement"),
                                        Step("address_in_footprint"), Step("hypothesis_agreement")), PLANS_GB.policy_rules, "lib-v0"),
    "soi_1inch": AdapterSpec("soi_1inch", (Step("graticule_frame"), Step("control_point_fit", {"model": "poly2", "crs": "EPSG:4326", "min_points": 6}),
                                          Step("residual_check", {"bound": 60.0, "geographic": True}), Step("plate_separation"), Step("line_structure"),
                                          Step("osm_reference"), Step("structure_match"), Step("hypothesis_agreement"),
                                          Step("cross_edition_agreement")), SOI_1INCH.policy_rules, "lib-v0"),
    "unlabelled_raster": AdapterSpec("unlabelled_raster", (Step("hint_area"), Step("edge_structure"), Step("reference_render"),
                                                          Step("structure_match_orb"), Step("overlay_agreement")), UNLABELLED_RASTER.policy_rules, "lib-v0"),
}


def validate(kind: str) -> list[str]:
    """Composition-only: every step of the kind's spec must be a library primitive. Empty list = valid."""
    return SPECS[kind].validate(names())


def unavailable(kind: str) -> list[str]:
    """Primitives the spec needs that are declared but not implemented on this machine."""
    return [s.primitive for s in SPECS[kind].steps if not LIBRARY[s.primitive].available()]


def registry_for(kind: str, stubs: dict | None = None) -> ToolRegistry:
    """Build the tool registry for a kind. `stubs` may supply implementations for declared-only primitives
    (tests, or a machine without the bound repositories)."""
    reg = ToolRegistry()
    stubs = stubs or {}
    for s in SPECS[kind].steps:
        p = LIBRARY[s.primitive]
        if s.primitive in reg:
            continue
        if s.primitive in stubs:                       # an explicit stub wins
            from ga.tools.registry import Tool
            reg.add(Tool(p.name, p.consumes, p.produces, p.family, p.deterministic, p.cost_estimate, stubs[s.primitive], p.about + " (stub)"))
        elif p.available():
            reg.add(p.tool(**s.params))
        else:
            raise RuntimeError(f"{kind}: primitive {s.primitive!r} is declared but not implemented here; pass a stub or install {p.requires}")
    return reg


def plan_for(kind: str) -> list[str]:
    return [s.primitive for s in SPECS[kind].steps]
