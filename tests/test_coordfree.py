"""The coordinate-free benchmark: the draw never opens an image, hints carry no sheet number, the window stays inside
the map body, its truth is the source georeference moved by the crop, and the scorer measures what it says."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "benchmarks"))
import numpy as np
import pytest

import coordfree as cf


def test_hints_drop_sheet_numbers_and_scales():
    assert cf.hints_for({"sheet": "Harrisville, WV (15')"}) == {"region": "West Virginia, United States",
                                                                 "title": "Harrisville, West Virginia, United States"}
    g = cf.hints_for({"sheet": "TK25 5215 (Meßtischblatt [5215 = 3042 =] 6 : Dillenburg, 1877)", "datum": "EPSG:4314"})
    assert g == {"region": "Germany", "title": "Dillenburg, Germany"}
    assert cf.hints_for({"sheet": "TK25 5051 (Section Sebnitz)", "datum": "EPSG:4314"})["title"] == "Sebnitz, Germany"
    assert cf.hints_for({"sheet": "TK25 7911 (Meßtischblatt Breisach (Alt))", "datum": "EPSG:4314"})["title"] == "Breisach, Germany"


def test_the_draw_is_seeded_and_reads_only_the_case_file(tmp_path):
    src = {"cases": [{"id": f"q{i}", "sheet": "Kanab, UT (15')", "bounds": [-112.75, 37.0, -112.5, 37.25],
                      "scans": ["a.tif", "b.tif"]} for i in range(5)] + [{"id": "ctl", "control": True, "scans": ["x"]}]}
    p = tmp_path / "src.json"; p.write_text(json.dumps(src))
    a, b = cf.draw(str(p), 7, None, "c"), cf.draw(str(p), 7, None, "c")
    assert a == b and len(a["cases"]) == 5
    for c in a["cases"]:
        fw, fh, ox, oy = c["window"]
        assert cf.WINDOW[0] <= fw <= cf.WINDOW[1] and cf.WINDOW[0] <= fh <= cf.WINDOW[1] and 0 <= ox <= 1 and 0 <= oy <= 1
    assert cf.draw(str(p), 8, None, "c") != a


@pytest.fixture
def geotiff_case(tmp_path):
    """A 1000 x 1200 px GeoTIFF in WGS84 whose sheet bounds sit 50 px inside the image (a collar)."""
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin
    W, H, px = 1000, 1200, 0.25 / 900
    T = from_origin(-71.0 - 50 * px, 42.5 + 50 * px * 1.2, px, px * 1.2)
    path = tmp_path / "sheet.tif"
    data = (np.random.default_rng(0).random((3, H, W)) * 255).astype("uint8")
    with rasterio.open(path, "w", driver="GTiff", width=W, height=H, count=3, dtype="uint8", crs="EPSG:4326", transform=T) as ds:
        ds.write(data)
    src = {"data_dir": str(tmp_path.relative_to(tmp_path.anchor)), "cases": [{"id": "q1", "sheet": "Boston Bay, MA (15')",
           "bounds": [-71.0, 42.25, -70.75, 42.5], "datum": "EPSG:4326", "scans": ["sheet.tif"]}]}
    return path, src, T, px


def test_window_inside_the_map_body_and_truth_follows_the_crop(geotiff_case, tmp_path, monkeypatch):
    path, src, T, px = geotiff_case
    from demo.run_demo import Truth
    truth = Truth(path)
    sc = src["cases"][0]
    for win in ([0.4, 0.4, 0.0, 0.0], [0.7, 0.7, 1.0, 1.0], [0.55, 0.45, 0.3, 0.8]):
        l, t, r, b = cf.window_px(truth, sc, win)
        body = (50 + cf.SHRINK * 900, 50 + cf.SHRINK * 750, 950 - cf.SHRINK * 900, 800 - cf.SHRINK * 750)   # sheet: 900 x 750 px
        assert l >= body[0] - 1 and t >= body[1] - 1 and r <= body[2] + 1 and b <= body[3] + 1
    # build one case end to end against this file
    monkeypatch.setattr(cf, "_scan_path", lambda s, c, k: path)
    srcf = tmp_path / "src.json"; srcf.write_text(json.dumps(src))
    case = cf.draw(str(srcf), 3, None, "c")
    case["source"] = str(srcf)
    casef = tmp_path / "cases.json"; casef.write_text(json.dumps(case))
    out = cf.build(str(casef), out=tmp_path / "built")
    tru = json.loads((out / "truth" / "c001.json").read_text())
    l, t, r, b = tru["window_px"]
    g = np.array(tru["grid_px"]) / tru["scale"]
    expect = np.c_[T.c + T.a * (l + g[:, 0] + 0.5), T.f + T.e * (t + g[:, 1] + 0.5)]
    assert np.abs(np.array(tru["grid_ll"]) - expect).max() < 1e-6
    img = __import__("PIL.Image", fromlist=["Image"]).open(out / "images" / "c001.jpg")
    assert list(img.size) == tru["size"] and not img.info.get("exif")


def test_scorer_measures_the_distance_it_says():
    g = cf.grid(1000, 800)
    k = 111320.0 * np.cos(np.radians(42.4))
    ll = np.c_[-71.0 + g[:, 0] * 1e-5, 42.5 - g[:, 1] * 1e-5]
    truth = {"grid_px": g.tolist(), "grid_ll": ll.tolist()}
    pairs = [[x, y, lo, la] for (x, y), (lo, la) in zip(g[::5], ll[::5])]
    assert cf.placement_error(pairs, truth)["max_m"] < 0.5
    moved = [[x, y, lo + 300 / k, la] for x, y, lo, la in pairs]          # the whole window 300 m east
    e = cf.placement_error(moved, truth)
    assert abs(e["median_m"] - 300) < 1 and abs(e["max_m"] - 300) < 1


def test_a_missing_answer_is_an_abstain(tmp_path, monkeypatch):
    casef = tmp_path / "c.json"
    casef.write_text(json.dumps({"source": "x", "cases": [{"id": "c001", "hints": {"region": "r", "title": "t"}}]}))
    (tmp_path / "truth").mkdir()
    g = cf.grid(100, 100)
    (tmp_path / "truth" / "c001.json").write_text(json.dumps({"grid_px": g.tolist(), "grid_ll": (np.c_[g[:, 0], -g[:, 1]] * 1e-5).tolist()}))
    good = [[x, y, x * 1e-5, -y * 1e-5] for x, y in g[::7]]
    res = cf.score(str(casef), {"c001": {"title": {"action": "accept", "pairs": good}}}, out=tmp_path)
    T = res["tally"]
    assert T["title"]["accepted right"] == 1 and T["none"]["abstain"] == 1 and T["region"]["abstain"] == 1
    assert [r["tier"] for r in res["rows"]] == list(cf.TIERS)
