"""An external family: the sheet's water against OpenStreetMap's water.

A placement made from the sheet's own graticule, checked against another scan of the same sheet, still rests on two
things the sheet and the record supply: the lines that were read and the bounds that label them. A wrong record, or
a misreading shared by two scans of one plate, passes both. This family uses neither: the sheet's blue plate
(hydrography: rivers, lakes, coast, which change far less than roads) is resampled onto a lon/lat grid through the
placement, OpenStreetMap's water is rendered onto the same grid, and the two are phase-correlated over an area one
graticule interval wider than the sheet on every side, so that a placement off by an interval shows as a shift of an
interval. Coordinates are moved between the placement's datum and WGS84 (OSM) with pyproj.

Reference data is fetched per sheet, only for the area it needs, the way a user with a handful of sheets would work:
OpenStreetMap vector tiles at zoom 13 from OpenFreeMap, pinned to one dated planet build so that results reproduce
(GA_OSM_TILES), cached on disk (GA_OSM_CACHE, default ~/.cache/anygeoreference/osm). Overpass is the alternative
(GA_OSM_SOURCE=overpass); it serves the live database, so its answers change.

Scope: maps that print water in a colour of its own (blue on USGS, OS, most topographic series). A monochrome or
greyscale scan yields no water and the check says "nothing to compare"; it never guesses.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
from pathlib import Path

import numpy as np

from . import Primitive, register
from evalcore import Evidence

# The default source: OpenStreetMap vector tiles (OpenMapTiles schema) from OpenFreeMap, pinned to one dated planet
# build so that the same sheet always meets the same reference. Fetched per sheet, only the tiles it needs.
TILES = os.environ.get("GA_OSM_TILES", "https://tiles.openfreemap.org/planet/20261101_080013_pt/{z}/{x}/{y}.pbf")
SOURCE = os.environ.get("GA_OSM_SOURCE", "tiles")              # "tiles" | "overpass"
OVERPASS = [m for m in os.environ.get("OSM_OVERPASS_URLS", "https://overpass-api.de/api/interpreter,"
            "https://overpass.kumi.systems/api/interpreter,https://overpass.private.coffee/api/interpreter").split(",") if m]
CACHE = Path(os.environ.get("GA_OSM_CACHE", Path.home() / ".cache" / "anygeoreference" / "osm"))
AGENT = "AnyGeoreference/0.1 (research benchmark; https://github.com/jiaazhaoo/AnyGeoreference)"
WATER_QUERY = """[out:json][timeout:180];
(
  way["waterway"~"^(river|stream|canal)$"]({s},{w},{n},{e});
  way["natural"="water"]({s},{w},{n},{e});
  way["natural"="coastline"]({s},{w},{n},{e});
  relation["natural"="water"]({s},{w},{n},{e});
);
out geom;"""


def osm_water(south: float, west: float, north: float, east: float, retries: int = 6) -> list[np.ndarray]:
    """OSM water as polylines (arrays of lon, lat in WGS84) intersecting the box. Cached; raises after retries."""
    import urllib.parse
    import urllib.request
    q = WATER_QUERY.format(s=round(south, 4), w=round(west, 4), n=round(north, 4), e=round(east, 4))
    key = hashlib.sha256(q.encode()).hexdigest()[:24]
    path = CACHE / f"water_{key}.json"
    if path.exists():
        data = json.loads(path.read_text())
    else:
        last = None
        for i in range(retries):
            url = OVERPASS[i % len(OVERPASS)]
            try:
                req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": q}).encode(), headers={"User-Agent": AGENT})
                with urllib.request.urlopen(req, timeout=240) as r:
                    data = json.load(r)
                break
            except Exception as e:                                       # noqa: BLE001  busy mirrors: back off, try the next
                last = e
                time.sleep(min(60, 5 * (i + 1)))
        else:
            raise RuntimeError(f"Overpass unavailable: {last}")
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
    lines = []
    for el in data.get("elements", []):
        geoms = [el.get("geometry")] if el.get("type") == "way" else [m.get("geometry") for m in el.get("members", [])]
        for g in geoms:
            if g and len(g) >= 2:
                lines.append(np.array([(p["lon"], p["lat"]) for p in g], float))
    return lines


def _tile_range(south, west, north, east, z):
    n = 2 ** z
    def xy(lon, lat):
        x = (lon + 180) / 360 * n
        y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
        return int(x), int(y)
    x0, y0 = xy(west, north); x1, y1 = xy(east, south)
    return range(x0, x1 + 1), range(y0, y1 + 1)


def _fetch_tile(z, x, y, retries: int = 5) -> bytes:
    import urllib.request
    url = TILES.format(z=z, x=x, y=y)
    path = CACHE / "tiles" / hashlib.sha256(url.encode()).hexdigest()[:24]
    if path.exists():
        return path.read_bytes()
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": AGENT})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            return data
        except Exception as e:                                           # noqa: BLE001
            if getattr(e, "code", None) == 404:                          # no tile: nothing there
                return b""
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"OSM tiles unavailable: {last}")


def osm_water_tiles(south: float, west: float, north: float, east: float, z: int = 13):
    """OSM water from vector tiles: (polygons, lines) in WGS84 lon/lat. Polygons are lists of rings (water areas:
    sea, lakes, wide rivers; clipped at tile edges, so they must be filled, never outlined, tile by tile); lines are
    waterways (rivers, streams, canals)."""
    import mapbox_vector_tile
    from concurrent.futures import ThreadPoolExecutor
    xs, ys = _tile_range(south, west, north, east, z)
    keys = [(x, y) for x in xs for y in ys]
    with ThreadPoolExecutor(4) as ex:
        blobs = list(ex.map(lambda k: _fetch_tile(z, *k), keys))
    n = 2 ** z
    def ll(x, y, gx, gy, ext):
        px = (x + np.asarray(gx, float) / ext) / n
        py = (y + np.asarray(gy, float) / ext) / n
        return np.c_[px * 360 - 180, np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * py))))]
    polys, lines = [], []
    for (x, y), blob in zip(keys, blobs):
        if not blob:
            continue
        d = mapbox_vector_tile.decode(blob, default_options={"y_coord_down": True})
        for f in d.get("water", {}).get("features", []):
            g = f["geometry"]; ext = d["water"].get("extent", 4096)
            parts = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"] if g["type"] == "MultiPolygon" else []
            for poly in parts:
                polys.append([ll(x, y, [p[0] for p in ring], [p[1] for p in ring], ext) for ring in poly if len(ring) >= 3])
        for f in d.get("waterway", {}).get("features", []):
            g = f["geometry"]; ext = d["waterway"].get("extent", 4096)
            parts = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"] if g["type"] == "MultiLineString" else []
            for ln in parts:
                if len(ln) >= 2:
                    lines.append(ll(x, y, [p[0] for p in ln], [p[1] for p in ln], ext))
    return polys, lines


def osm_reference(south, west, north, east):
    """(polygons, lines, source label) from the configured source."""
    if SOURCE == "overpass":
        return [], osm_water(south, west, north, east), "OSM via Overpass (live)"
    polys, lines = osm_water_tiles(south, west, north, east)
    return polys, lines, "OSM via OpenFreeMap " + TILES.split("/planet/")[-1].split("/")[0] if "/planet/" in TILES else TILES


def water_mask(rgb: np.ndarray, lift: int = 18) -> np.ndarray:
    """The blue plate of a printed map, relative to its own paper: old paper yellows, so blue ink is not blue in
    absolute terms but bluer than the paper. A greyscale scan yields (almost) nothing, and the check then abstains."""
    a = rgb.astype(np.int16)
    bi = a[..., 2] - (a[..., 0] + a[..., 1]) // 2
    s = a.sum(-1)
    bright = s > np.percentile(s, 80)
    paper = float(np.median(bi[bright])) if bright.any() else 0.0
    return ((bi - paper) > lift) & (s < 690)


def rgb_of(path: str) -> np.ndarray:
    import cv2
    if path.lower().endswith((".tif", ".tiff")):
        import rasterio
        with rasterio.open(path) as ds:
            arr = ds.read([1, 2, 3]) if ds.count >= 3 else np.repeat(ds.read([1]), 3, axis=0)
        return np.ascontiguousarray(arr.transpose(1, 2, 0))
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(path)
    return np.ascontiguousarray(img[..., ::-1])


def query_box(bounds, interval_min: float, crs: str, margin: float = 1.0) -> tuple:
    """The OSM box (south, west, north, east in WGS84) for a sheet: its bounds widened by `margin` intervals, moved
    from the sheet's datum, padded by 0.01 deg. One function, so a prefetch and the check ask Overpass the same thing."""
    from pyproj import Transformer
    west, south, east, north = bounds
    pad = margin * interval_min / 60.0
    lo, la = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform([west - pad, east + pad], [south - pad, north + pad])
    return min(la) - 0.01, min(lo) - 0.01, max(la) + 0.01, max(lo) + 0.01


def basemap_shift(rgb: np.ndarray, coeffs: np.ndarray, model: str, crs: str, bounds, interval_min: float,
                  res_m: float = 30.0, margin: float = 1.0, min_water: float = 0.002):
    """The sheet's water and OSM's water on one lon/lat grid (the placement's datum) over the bounds widened by
    `margin` intervals; the shift that best aligns them. Returns a dict: dx_m, dy_m, response, or why=None-reason."""
    import cv2
    from pyproj import Transformer
    from .graticule import warp_to_grid
    m = water_mask(rgb)
    west, south, east, north = bounds
    pad = margin * interval_min / 60.0
    big = (west - pad, south - pad, east + pad, north + pad)
    edges = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))   # areas -> outlines
    sheet, covered, (lons, lats) = warp_to_grid(255 - edges * 255, coeffs, model, big, res_m)
    water = float((sheet > 40)[covered].mean()) if covered.any() else 0.0
    if water < min_water:
        return {"why": f"too little water on the sheet ({water:.2%} of the placed area) to compare"}
    from_wgs = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    polys, lines, source = osm_reference(*query_box(bounds, interval_min, crs, margin))
    if not polys and not lines:
        return {"why": "OpenStreetMap has no water here"}
    dlon, dlat = lons[1] - lons[0], lats[0] - lats[1]
    def to_px(c):
        x, y = from_wgs.transform(c[:, 0], c[:, 1])
        return np.round(np.c_[(np.asarray(x) - lons[0]) / dlon, (lats[0] - np.asarray(y)) / dlat]).astype(np.int32)
    area = np.zeros(sheet.shape, np.uint8)
    for rings in polys:                                    # water areas filled across tiles, then outlined like the sheet's
        cv2.fillPoly(area, [to_px(r) for r in rings], 1)
    ref = cv2.morphologyEx(area, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) * 255
    for ln in lines:
        cv2.polylines(ref, [to_px(ln)], False, 255, 2)
    a = cv2.GaussianBlur(sheet.astype(np.float32), (0, 0), 1.5)
    b = cv2.GaussianBlur(ref.astype(np.float32), (0, 0), 1.5)
    if float((b > 40).mean()) < min_water:
        return {"why": "OpenStreetMap has too little water here to compare"}
    win = cv2.createHanningWindow((a.shape[1], a.shape[0]), cv2.CV_32F)
    (dx, dy), resp = cv2.phaseCorrelate(a, b, win)
    return {"dx_m": dx * res_m, "dy_m": -dy * res_m, "response": float(resp), "water": water,
            "osm_lines": len(lines), "osm_areas": len(polys), "source": source}


def basemap_agreement(state, tol_m: float = 150.0, min_response: float = 0.05):
    """Primitive: the best placement's water against OpenStreetMap's. Evidence basemap_agree True (shift within tol_m;
    150 m: on development data right placements shift by 23 m median, 68 m at the 95th and 123 m at the 99th
    percentile, and a wrong one 189 m off showed 208 m), 
    False (a clear correlation at a larger shift: the placement or the record is off), None (no water, no OSM water,
    no clear correlation, OSM unreachable)."""
    from .graticule import _fit_of
    rec = {**dict(state.sheet.meta), **dict(state.sheet.record)}
    if not state.hypotheses or not rec.get("bounds"):
        return []
    h = state.hypotheses[0]
    try:
        coeffs, model = _fit_of(h)
    except (ValueError, SyntaxError, IndexError):
        return [Evidence("basemap_agree", None, "deterministic", "basemap", note="a placement without fit coefficients")]
    try:
        r = basemap_shift(rgb_of(state.sheet.image), coeffs, model, h.crs, [float(v) for v in rec["bounds"]],
                          float(rec.get("interval_min", 5.0)))
    except RuntimeError as e:
        return [Evidence("basemap_agree", None, "deterministic", "basemap", note=str(e)[:160])]
    if "why" in r:
        return [Evidence("basemap_agree", None, "deterministic", "basemap", note=r["why"])]
    d = math.hypot(r["dx_m"], r["dy_m"])
    if r["response"] < min_response:
        return [Evidence("basemap_agree", None, "deterministic", "basemap",
                         note=f"water does not correlate with OSM (response {r['response']:.3f}, shift {d:.0f} m); nothing to compare")]
    return [Evidence("basemap_agree", bool(d <= tol_m), "deterministic", "basemap",
                     note=f"water vs OSM: shift {d:.0f} m (dx {r['dx_m']:+.0f}, dy {r['dy_m']:+.0f}), response {r['response']:.3f}, "
                          f"sheet water {r['water']:.1%}, {r['osm_areas']} areas + {r['osm_lines']} lines from {r['source']}; tol {tol_m} m"),
            Evidence("basemap_shift_m", round(d, 1), "deterministic", "basemap")]


register(Primitive("basemap_agreement", "basemap", True, ("hypothesis",), "evidence",
                   "the sheet's blue plate (water) resampled through the placement vs OpenStreetMap water, phase-correlated over an "
                   "area one interval wider than the sheet: a placement or a record off by an interval shows as that shift",
                   basemap_agreement, "generic", requires=("opencv", "Overpass")))
