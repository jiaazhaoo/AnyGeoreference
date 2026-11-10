"""World gazetteer and names-as-geometry: name matching rules, and the name fit on a synthetic sheet whose labels sit
beside features of a fake gazetteer (no network)."""
import math

import numpy as np
import pytest

from ga import gazetteer as gz
from ga.model import Candidate, Cue, Sheet


@pytest.mark.parametrize("read,gaz,same", [
    ("Mt Carmel Junction", "Mount Carmel Junction", True),
    ("Hut Bg.", "Hutberg", True),
    ("Wallpack Cem", "Walpack Cemetery", True),
    ("Buttermilch M.", "Buttermilchmühle", True),
    ("Dänschenburg", "Daenschenburg", True),
    ("Delaware RIVER", "Delaware River", True),
    ("Virgin", "East Fork Virgin River", False),
    ("Twin Hollow", "Twin Hollows Campground", False),
    ("Spring", "Spring Creek", False),
    ("Red Knoll", "Red Knob", False),
])
def test_name_match(read, gaz, same):
    assert gz.name_match(read, gaz) is same


def test_distinctive_words_drop_shared_and_abbreviated():
    w = gz.distinctive_words(["Moncur Spring", "Yellowjacket Spring", "Twin Hollow", "Monument Hollow", "Hut Bg."])
    assert "spring" not in w and "hollow" not in w and "bg" not in w
    assert {"moncur", "yellowjacket", "twin", "monument", "hut"} <= set(w)


def _sheet_and_world(shift_px=(0, 0)):
    """A 2000 x 1500 px sheet at 5 m/px, north up, top-left at (lon 10.0, lat 50.0) roughly; eight named features,
    labels drawn 20 px to the right of each."""
    from pyproj import Transformer
    crs = "EPSG:32632"
    to_ll = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    to_xy = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    x0, y0 = to_xy.transform(10.0, 50.0)
    names = ["Alderbrook", "Birchholt", "Cranmoor", "Dunhallow", "Elmswick", "Fernlea", "Gorsedown", "Hazelmere"]
    rng = np.random.default_rng(1)
    px = rng.uniform([100, 100], [1900, 1400], size=(len(names), 2))
    feats, cues = [], []
    for nm, (x, y) in zip(names, px):
        lon, lat = to_ll.transform(x0 + 5 * x, y0 - 5 * y)
        feats.append(gz.Place(nm, (nm,), lon, lat, (lon, lat, lon, lat), "place=hamlet"))
        lx, ly = x + 20 + shift_px[0], y + shift_px[1]
        cues.append(Cue("d", "place", nm, (lx - 30, ly - 8, lx + 30, ly + 8), "claude_read", 0.9))
    # a homonym far away and an unrelated name
    feats.append(gz.Place("Cranmoor", ("Cranmoor",), 10.3, 49.8, (10.3, 49.8, 10.3, 49.8), "place=hamlet"))
    cues.append(Cue("d", "landmark", "Spring", (500, 500, 560, 516), "claude_read", 0.9))
    sheet = Sheet("s1", "map_extract", "x.jpg", "d", {"hint": ""}, {"width": 2000, "height": 1500})
    truth = lambda x, y: to_ll.transform(x0 + 5 * x, y0 - 5 * y)
    return sheet, cues, feats, truth


def test_name_fit_places_a_synthetic_sheet(monkeypatch):
    from ga.loop import State
    from ga.primitives.names_world import name_fit
    sheet, cues, feats, truth = _sheet_and_world()
    monkeypatch.setattr(gz, "features", lambda box, names, **k: feats)
    monkeypatch.setattr(gz, "search", lambda name, area=None, limit=40: [])
    st = State(sheet)
    st.cues.extend(cues)
    st.candidates.append(Candidate("d", "gazetteer", "POLYGON((9.8 49.7,10.4 49.7,10.4 50.1,9.8 50.1,9.8 49.7))", "EPSG:4326", (), 0.5))
    hyps = name_fit(st)
    assert hyps, [e.note for e in st.evidence]
    h = hyps[0]
    facts = {e.name: e.value for e in st.evidence}
    assert facts["names_agree"] == 8
    from pyproj import Transformer
    to_ll = Transformer.from_crs(h.crs, "EPSG:4326", always_xy=True)
    a, b, c, d, e, f = h.transform
    for x, y in ((0, 0), (2000, 1500), (1000, 750)):
        lon, lat = to_ll.transform(a * x + b * y + c, d * x + e * y + f)
        tl = truth(x, y)
        err = math.hypot((lon - tl[0]) * 111320 * math.cos(math.radians(lat)), (lat - tl[1]) * 110574)
        assert err < 200, err                     # the labels sit 20 px (100 m) beside their features


def test_name_search_area_clusters_different_names(monkeypatch):
    from ga.loop import State
    from ga.primitives.names_world import name_search_area
    sheet, cues, feats, _ = _sheet_and_world()
    by = {}
    for p in feats:
        by.setdefault(p.name, []).append(p)
    far = gz.Place("Alderbrook", ("Alderbrook",), -100.0, 40.0, (-100.0, 40.0, -100.0, 40.0), "place=hamlet")
    monkeypatch.setattr(gz, "search", lambda name, area=None, limit=40: by.get(name, []) + ([far] if name == "Alderbrook" else []))
    st = State(sheet)
    st.cues.extend(cues)
    out = name_search_area(st)
    assert out and out[0].source == "gazetteer"
    import shapely.wkt
    w, s, e, n = shapely.wkt.loads(out[0].area_wkt).bounds
    assert w < 10.0 < e and s < 50.0 < n
    assert len(out[0].answers) == 8


def test_water_refine_corrects_shift_and_scale(monkeypatch):
    """A names placement 2% too large and 200 m off; the water (faked: the true offset at the sheet centre and at the
    quadrant centres) moves it back within a few metres, and the quadrants then agree."""
    from pyproj import Transformer
    from ga.loop import State
    from ga.model import Hypothesis
    from ga.primitives import basemap
    from ga.primitives.generic import apply_transform
    from ga.primitives.names_world import water_refine
    crs = "EPSG:32632"
    to_ll = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    W, H = 2000, 1500
    x0, y0 = 500000.0, 5540000.0
    truth = (5.0, 0.0, x0, 0.0, -5.0, y0)
    wrong = (5.1, 0.0, x0 + 150.0, 0.0, -5.1, y0 - 130.0)

    def fake_shift(rgb, coeffs, model, crs_, bounds, interval_min, res_m=20.0, margin=1.0, **k):
        def off(px):
            lon, lat = apply_transform(coeffs, np.array([px], float), model)[0]
            tx, ty = truth[0] * px[0] + truth[2], truth[4] * px[1] + truth[5]
            tlon, tlat = to_ll.transform(tx, ty)
            return ((tlon - lon) * 111320 * math.cos(math.radians(lat)), (tlat - lat) * 110574)
        g = off((W / 2, H / 2))
        local = [dict(zip(("dx_m", "dy_m"), off(p)), response=0.2) for p in ((W / 4, H / 4), (3 * W / 4, H / 4), (W / 4, 3 * H / 4), (3 * W / 4, 3 * H / 4))]
        return {"dx_m": g[0], "dy_m": g[1], "response": 0.2, "water": 0.05, "osm_lines": 1, "osm_areas": 1, "source": "fake", "local": local}

    monkeypatch.setattr(basemap, "basemap_shift", fake_shift)
    monkeypatch.setattr(basemap, "rgb_of", lambda path: None)
    sheet = Sheet("s1", "map_extract", "x.jpg", "d", {}, {"width": W, "height": H})
    st = State(sheet)
    st.hypotheses.append(Hypothesis("d", wrong, "POLYGON EMPTY", crs, 0.8, "name_fit"))
    ev = {e.name: e.value for e in water_refine(st)}
    assert ev["water_locked"] is True and ev["water_local_agree"] is True
    h = st.hypotheses[0]
    assert h.matcher == "name_fit+water"
    a, b, c, d, e, f = h.transform
    for x, y in ((0, 0), (W, H), (W, 0)):
        err = math.hypot(a * x + b * y + c - (truth[0] * x + truth[2]), d * x + e * y + f - (truth[4] * y + truth[5]))
        assert err < 30, err
