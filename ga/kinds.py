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
    cues=("road", "number", "grid", "place"),            # read by Claude (claude_read) and by OCR + label rules
    references=("gazetteer", "address-register", "road-network", "basemap"),
    matchers=("text_anchor_fit", "grid_figures", "plan_minima_match", "structure_match_orb"),
    verifications=("address_in_footprint", "overlay_agreement", "snap_faces", "hypothesis_agreement"),
    policy_rules=(
        # provisional, fitted on ten graded drawings (2026-11-06, docs/FINDINGS.md): a learned-matcher score >= 50
        # alone accepted a 736 m miss; with the address point inside the footprint it accepted 2, both right
        {"id": "no_location_cues", "when": "n_location_cues == 0", "to": "abstain"},
        {"id": "snap_and_address", "when": "(snap_iou or 0) >= 0.86 and address_inside", "to": "accept"},
        {"id": "anchors_and_address", "when": "best_matcher == 'text_anchor_fit' and (best_score or 0) >= 0.75 and address_in_footprint", "to": "accept"},
        {"id": "learned_match_and_address", "when": "best_matcher == 'plan_minima_match' and (best_score or 0) >= 0.5 and address_in_footprint", "to": "accept"},
        {"id": "address_and_overlay", "when": "address_in_footprint and (overlay_agreement or 0) >= 0.3", "to": "accept"},
        {"id": "two_matchers_agree", "when": "matchers_agree and address_in_footprint", "to": "accept"},
        {"id": "far_from_record", "when": "(address_to_centre_m or 0) > 2000", "from": "accept", "to": "review"},
    ),
    expected_accuracy_m=(2.0, 10.0), expected_cost_per_sheet=0.012,
    note="truth: the client's verdict on delivered polygons; abstain when neither snap nor address agrees")

SOI_1INCH = Recipe(
    name="soi_1inch", kind="historical_map",
    profile=Profile("Survey of India 1-inch / quarter-inch sheet, 1910s-40s", (), ("black", "red", "blue", "green", "yellow"),
                    ("place", "elevation", "gothic"), printed_grid="graticule", scale_hint="1:63360", era="1910-1945",
                    measured_by={"colour_plates": "plates.separate", "printed_grid": "frame.detect"}),
    cues=("grid", "place"),
    references=("record-text", "basemap"),
    matchers=("control_point_fit", "structure_match"),
    verifications=("residual_check", "cross_edition_agreement", "overlay_agreement"),
    policy_rules=(
        # a small residual at the graticule nodes proves self-consistency only: a frame read one graticule line off
        # keeps a 20 m residual and lands 9 km away (053ASE 1943 edition, 2026-11-06). Accept needs a second family.
        {"id": "residual_and_structure", "when": "residual_within_bound and matchers_agree == True", "to": "accept"},
        # not for a frame read by its corners alone: two editions share the frame and the content, so they agree when the
        # sheet's content sits off its own graticule (seen on 19th-century sheets, 150-250 m); only the external check sees it
        {"id": "residual_and_edition", "when": "residual_within_bound and editions_agree == True and graticule_frame_only != True", "to": "accept"},
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

STREET_MAP = Recipe(
    name="street_map", kind="street_map",
    profile=Profile("a town plan, street map or rendered map carrying street and place names, any era", (), (), ("road", "place", "landmark"),
                    printed_grid="none", measured_by={"text_kinds": "model reading"}),
    cues=("road", "place", "landmark"),
    references=("gazetteer", "road-network"),
    matchers=("road_name_fit",),
    verifications=("places_in_footprint", "hypothesis_agreement"),
    policy_rules=(
        # fitted on two blind inputs (2026-11-06): an 1823 engraved plan and an OSM-style render; provisional
        {"id": "no_location_cues", "when": "n_location_cues == 0", "to": "abstain"},
        {"id": "roads_and_places", "when": "best_matcher == 'road_name_fit' and (best_score or 0) >= 0.5 and (places_in_footprint or 0) >= 2", "to": "accept"},
    ),
    expected_accuracy_m=(30.0, 400.0), expected_cost_per_sheet=0.0,
    note="labels on their named roads is the matcher; place names inside the footprint is the second family; old maps get a wider tolerance")

SURVEY_GRATICULE = Recipe(
    name="survey_graticule", kind="historical_map",
    profile=Profile("any survey sheet with a neatline and a printed graticule: lines across the map, edge ticks and interior crosses, or the labelled neatline alone (USGS quadrangles, German 1:25,000 sheets, 1870s-1970s)", (), (),
                    ("grid",), printed_grid="graticule", scale_hint="1:62500 / 1:24000", era="1880-1980",
                    measured_by={"printed_grid": "graticule_marks"}),
    cues=("grid",),
    references=("record-text", "basemap"),
    matchers=("control_point_fit",),
    verifications=("residual_check", "basemap_agreement", "edition_agreement"),
    policy_rules=(
        # the residual at the nodes proves self-consistency only (see soi_1inch): accept needs a second family, another
        # edition placed on its own (same content in the same place) or the sheet's water against OpenStreetMap's
        # not for a frame read by its corners alone: two editions share the frame and the content, so they agree when the
        # sheet's content sits off its own graticule (seen on 19th-century sheets, 150-250 m); only the external check sees it
        {"id": "residual_and_edition", "when": "residual_within_bound and editions_agree == True and graticule_frame_only != True", "to": "accept"},
        {"id": "residual_and_basemap", "when": "residual_within_bound and basemap_agree == True", "to": "accept"},
        {"id": "editions_disagree", "when": "editions_agree == False", "from": "accept", "to": "review"},
        # editions agree with each other when the record is wrong or both scans were misread alike; an external
        # reference that disagrees outranks them
        {"id": "basemap_disagrees", "when": "basemap_agree == False", "from": "accept", "to": "review"},
        # two scans that agree share their fate: the partner shown wrong by the external reference takes this one along
        {"id": "partner_shown_wrong", "when": "editions_agree == True and partner_basemap_agree == False", "from": "accept", "to": "review"},
        {"id": "graticule_ambiguous", "when": "graticule_ambiguous == True", "from": "accept", "to": "review"},
    ),
    expected_accuracy_m=(10.0, 40.0), expected_cost_per_sheet=0.0,
    note="truth: the archive's published georeference (USGS GeoTIFF), never read by the loop; bounds and interval from the record; OSM water is a reference, not truth")

KINDS = {r.name: r for r in (PLANS_GB, SOI_1INCH, UNLABELLED_RASTER, STREET_MAP, SURVEY_GRATICULE)}

# the ordered composition each kind runs (the FixedPlan); the Planner picks from the same names
SPECS = {
    "plans_gb": AdapterSpec("plans_gb", (Step("claude_read"), Step("ocr_cached"), Step("road_and_place_labels"), Step("gazetteer_search"), Step("grid_figures"),
                                        Step("text_anchor_fit"), Step("plan_minima_match"), Step("edge_structure"), Step("reference_render", {"res_m": 1.0}),
                                        Step("overlay_agreement"), Step("address_in_footprint"), Step("hypothesis_agreement")), PLANS_GB.policy_rules, "lib-v0"),
    "soi_1inch": AdapterSpec("soi_1inch", (Step("sheet_index_lookup"), Step("graticule_frame"), Step("control_point_fit", {"model": "poly2", "crs": "EPSG:4326", "min_points": 6}),
                                          Step("residual_check", {"bound": 60.0, "geographic": True}), Step("plate_separation"), Step("line_structure"),
                                          Step("osm_reference"), Step("structure_match"), Step("hypothesis_agreement"),
                                          Step("cross_edition_agreement")), SOI_1INCH.policy_rules, "lib-v0"),
    "street_map": AdapterSpec("street_map", (Step("claude_read", {"headless": True}), Step("place_lookup"), Step("road_junction_locate"), Step("road_name_fit"),
                                            Step("places_in_footprint"), Step("hypothesis_agreement")), STREET_MAP.policy_rules, "lib-v0"),
    "survey_graticule": AdapterSpec("survey_graticule", (Step("graticule_marks"), Step("control_point_fit", {"model": "poly2", "crs": "EPSG:4267", "min_points": 6, "fallback": "affine"}),
                                                        Step("residual_check", {"bound": 30.0, "geographic": True}), Step("basemap_agreement"),
                                                        Step("edition_agreement")),
                                    SURVEY_GRATICULE.policy_rules, "lib-v0"),
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


class _Facts(dict):
    """Facts for a rule's condition: a fact no step produced reads as None, never as an error."""
    def __missing__(self, key):
        return None


def policy_for(kind: str):
    """The kind's policy rules as an evalcore Policy (default: review)."""
    from evalcore import Policy, Rule
    rules = [Rule(r["id"], (lambda f, e=r["when"]: bool(eval(e, {"__builtins__": {}}, _Facts(f)))), r["to"],
                  (r["from"],) if "from" in r else None, when_text=r["when"]) for r in KINDS[kind].policy_rules]
    return Policy(f"{kind}-rules", "v0", rules)
