import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ga.knowledge import Index, load

SECTIONS = {"routing", "family", "reading", "reference", "geodesy", "transforms", "matcher", "verify", "truth", "failure", "operate", "build", "literature"}
FAMILIES = {"sheet-reader", "record-text", "gazetteer", "address-register", "road-network", "basemap", "geometry"}


def test_every_card_is_well_formed():
    cards = load()
    ids = {c.id for c in cards}
    assert len(cards) >= 70 and len(ids) == len(cards)
    for c in cards:
        assert c.section in SECTIONS, c.id
        assert c.method and len(c.text.split()) >= 80, c.id                     # a card says something
        assert c.kinds and c.tags, c.id
        for s in c.see:
            assert s in ids, f"{c.id} links to unknown card {s}"
        assert c.id == os.path.basename(c.path)[:-3]
        if c.buildable:
            assert c.buildable in ("yes", "no") and c.effort, c.id


def test_named_primitives_exist_in_the_library():
    from ga.primitives import LIBRARY
    missing = {(c.id, p) for c in load() for p in c.primitives if p not in LIBRARY}
    assert not missing, missing


def test_retrieval_routes_the_classic_queries():
    idx = Index()
    def top(q, **kw):
        return [c.id for _, c in idx.retrieve(q, k=kw.pop("k", 3), **kw)]
    assert top("printed graticule corner coordinates polynomial residual", kind="historical_map", cues=["grid"])[0] in ("family-survey-graticule", "matcher-graticule-corners")
    assert "matcher-text-anchors" in top("house numbers road names address register", kind="planning_drawing", cues=["number"])
    assert "matcher-street-names-geometry" in top("many street names no house numbers town plan", cues=["road"], k=5)
    assert top("many street names no house numbers town plan", cues=["road"])[0] == "family-town-plans"
    assert "matcher-toponym-constellation" in top("place names only no roads county map gazetteer")
    assert "matcher-polyline-shape" in top("coastline river shape no readable text chart")
    assert "geodesy-datums-and-shifts" in top("uniform offset 100 m against WGS84 printed latitude longitude")
    assert "failure-one-line-off" in top("perfect residual but 9 km off graticule interval")
    assert "family-oblique-photos" in top("oblique photograph perspective viewpoint", k=4)
    assert "matcher-parcel-boundaries" in top("tithe map parcel acreage apportionment", k=4)
    assert "family-survey-graticule" not in top("anything", kind="planning_drawing", k=40)   # kind filter


def test_catalogue_marks_library_and_buildable():
    idx = Index()
    cat = idx.catalogue(library={"road_junction_locate": 1, "road_name_fit": 1, "places_in_footprint": 1}, hidden=set())
    assert "[matcher-street-names-geometry] -> in library: road_junction_locate, road_name_fit, places_in_footprint" in cat
    hid = idx.catalogue(library={"road_junction_locate": 1, "road_name_fit": 1, "places_in_footprint": 1}, hidden={"road_name_fit"})
    assert "missing: road_name_fit | buildable: yes" in hid
    assert "[matcher-toponym-constellation] -> NOT in library | buildable: yes" in cat
    assert "[family-oblique-photos] -> NOT in library | not buildable here" in cat
