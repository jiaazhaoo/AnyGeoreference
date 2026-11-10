"""A world gazetteer, fetched per sheet: OpenStreetMap through its two public query services.

  - search(name, area): Nominatim, the OSM geocoder; one request per name, at most one request a second (its usage
    policy), every answer cached. Used to find WHERE a sheet's names occur together when nothing else says.
  - features_in(bbox, names): Overpass; one request per sheet and area, the named features (points, lines, areas)
    whose names contain the sheet's distinctive words. Used to fit the sheet once the area is known.
  - name_match(read, gazetteer): is a label as printed the same name as a gazetteer entry? Case, accents, spacing,
    compounds ("Hut Bg." / "Hutberg") and abbreviations ("Mt" / "Mount", "Cem" / "Cemetery") are tolerated; a label
    that is only part of a longer name ("Virgin" / "East Fork Virgin River") is not the same name.

Nothing is downloaded in bulk: a sheet costs one request per name read plus one per area, the way a user with a
handful of sheets would work. OSM is live, so answers can change; the cache (GA_GAZETTEER_CACHE, default
~/.cache/anygeoreference/gazetteer) is the record of what a run saw. Endpoints: GA_NOMINATIM, OSM_OVERPASS_URLS.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np

NOMINATIM = os.environ.get("GA_NOMINATIM", "https://nominatim.openstreetmap.org")
OVERPASS = [m for m in os.environ.get("OSM_OVERPASS_URLS", "https://overpass-api.de/api/interpreter,"
            "https://overpass.private.coffee/api/interpreter,https://overpass.kumi.systems/api/interpreter").split(",") if m]
CACHE = Path(os.environ.get("GA_GAZETTEER_CACHE", Path.home() / ".cache" / "anygeoreference" / "gazetteer"))
AGENT = "AnyGeoreference/0.1 (research benchmark; https://github.com/jiaazhaoo/AnyGeoreference)"
NAME_KEYS = ("name", "alt_name", "old_name", "official_name", "short_name", "loc_name")

_lock = threading.Lock()
_last = [0.0]


@dataclass(frozen=True)
class Place:
    name: str
    names: tuple[str, ...]                 # every name the entry carries (name, alt_name, old_name, name:xx ...)
    lon: float                             # a representative point
    lat: float
    bbox: tuple[float, float, float, float]   # west, south, east, north
    kind: str                              # "class=type" from OSM
    shape: tuple = ()                      # vertices (lon, lat) of a line or an area's outline; () for a point
    area: bool = False                     # True: the shape is a closed outline and the name labels its inside

    def extent_m(self) -> float:
        w, s, e, n = self.bbox
        return math.hypot((e - w) * 111320 * math.cos(math.radians((s + n) / 2)), (n - s) * 110574)


# -- names --------------------------------------------------------------------------------------------------------
def fold(s: str) -> str:
    s = str(s).replace("ß", "ss").replace("ẞ", "ss")
    s = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in s if not unicodedata.combining(ch)).lower()


def tokens(s: str) -> list[tuple[str, bool]]:
    """Folded word tokens of a label, each with an 'abbreviated' flag (written with a full stop, or 1-3 letters)."""
    out = []
    for m in re.finditer(r"[^\W_]+(\.?)", fold(s)):
        t = m.group(0).rstrip(".")
        if t.isdigit():
            continue
        out.append((t, bool(m.group(1)) or len(t) <= 3))
    return out


def _subseq(a: str, b: str) -> bool:
    it = iter(b)
    return all(ch in it for ch in a)


def _tok_ok(r: str, abbr: bool, g: str) -> bool:
    if r == g:
        return True
    if abbr and len(g) > len(r) and r[0] == g[0] and _subseq(r, g):
        return True
    return len(r) >= 5 and len(g) >= 5 and SequenceMatcher(None, r, g).ratio() >= 0.88    # one letter more or less


def _align(rt: list, gt: list) -> bool:
    if not rt:
        return not gt
    if not gt:
        return False
    (r, abbr), g = rt[0], gt[0]
    if _tok_ok(r, abbr, g) and _align(rt[1:], gt[1:]):
        return True
    for k in range(2, len(g) - 1):                     # a compound: this word is the head of the gazetteer's word
        if (g[:k] == r or (abbr and _tok_ok(r, abbr, g[:k]))) and len(rt) > 1 and _align(rt[1:], [g[k:]] + gt[1:]):
            return True
    return False


def name_match(read: str, gaz: str) -> bool:
    rt, gt = tokens(read), [t for t, _ in tokens(gaz)]
    if not rt or not gt:
        return False
    if len(rt) == 1:                                   # a one-word name is written out: "Fork" is not "Fort Knox"
        rt = [(rt[0][0], False)]
    a, b = "".join(t for t, _ in rt), "".join(gt)
    if a == b:
        return True
    if len(a) >= 6 and SequenceMatcher(None, a, b).ratio() >= 0.88:
        return True
    return _align(rt, gt)


def matches(read: str, place: Place) -> bool:
    return any(name_match(read, n) for n in place.names)


# -- Nominatim ----------------------------------------------------------------------------------------------------
def _get(url: str, cache_name: str, retries: int = 4, pace: float = 0.0, data: bytes | None = None, timeout: int = 120):
    path = CACHE / cache_name
    if path.exists():
        return json.loads(path.read_text())
    last = None
    for i in range(retries):
        if pace:
            with _lock:
                wait = _last[0] + pace - time.time()
                if wait > 0:
                    time.sleep(wait)
                _last[0] = time.time()
        try:
            u = url[i % len(url)] if isinstance(url, list) else url
            req = urllib.request.Request(u, data=data, headers={"User-Agent": AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                out = json.load(r)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(out))
            return out
        except Exception as e:                                       # noqa: BLE001  busy server: back off, retry
            last = e
            time.sleep(min(60, 5 * (i + 1)))
    raise RuntimeError(f"gazetteer unavailable: {last}")


def _place_from_nominatim(r: dict) -> Place:
    nd = r.get("namedetails") or {}
    names = tuple(dict.fromkeys([r.get("name") or ""] + [v for k, v in nd.items() if k in NAME_KEYS or k.startswith("name:")]))
    s, n, w, e = (float(v) for v in r["boundingbox"])
    return Place(r.get("name") or "", tuple(x for x in names if x), float(r["lon"]), float(r["lat"]), (w, s, e, n),
                 f"{r.get('category', r.get('class', ''))}={r.get('type', '')}")


def search(name: str, area: tuple | None = None, limit: int = 40) -> list[Place]:
    """Nominatim free-text search for one name, worldwide or inside area=(west, south, east, north)."""
    p = {"format": "jsonv2", "q": name, "limit": str(limit), "namedetails": "1"}
    if area:
        w, s, e, n = area
        p.update(viewbox=f"{w:.4f},{n:.4f},{e:.4f},{s:.4f}", bounded="1")
    url = f"{NOMINATIM}/search?" + urllib.parse.urlencode(p)
    key = hashlib.sha256(url.encode()).hexdigest()[:24]
    return [_place_from_nominatim(r) for r in _get(url, f"nominatim/{key}.json", pace=1.1) if r.get("boundingbox")]


def area_of(text: str, min_half_m: float = 60000.0) -> tuple | None:
    """The area a place name in the record stands for, (west, south, east, north): its outline's box, at least
    min_half_m either side of it (a map named after a town covers country around the town)."""
    hits = search(text, limit=1)
    if not hits:
        return None
    p = hits[0]
    w, s, e, n = p.bbox
    dlat = min_half_m / 110574
    dlon = min_half_m / (111320 * math.cos(math.radians(p.lat)))
    return (min(w, p.lon - dlon), min(s, p.lat - dlat), max(e, p.lon + dlon), max(n, p.lat + dlat))


def box_side_m(bbox) -> float:
    w, s, e, n = bbox
    return max((e - w) * 111320 * math.cos(math.radians((s + n) / 2)), (n - s) * 110574)


# -- Overpass -----------------------------------------------------------------------------------------------------
def distinctive_words(names: list[str]) -> list[str]:
    """The words worth asking for: of three letters or more, written out (no full stop), and not shared by two different names
    on the sheet (a word every second label carries, 'Spring', 'Berg', 'Creek', says what a thing is, not which). Each
    word as printed (lower case, accents kept: OSM keeps them too) and, when it differs, folded to ASCII."""
    per = [{m.group(1) for m in re.finditer(r"([^\W\d_]{3,})(?![\w.])", str(n).lower())} for n in names]
    count: dict[str, int] = {}
    for ws in per:
        for w in {fold(x) for x in ws}:
            count[w] = count.get(w, 0) + 1
    out = set()
    for ws in per:
        for w in ws:
            if count[fold(w)] == 1:
                out |= {w, fold(w)}
    return sorted(out)


def _overpass_regex(words: list[str]) -> str:
    # a word of the sheet starts a word of the name (or a compound: "Hut" in "Hutberg"), never sits inside one
    return "(^|[ -])(" + "|".join(re.escape(w) for w in words) + ")"


def features_in(bbox, names: list[str], max_words: int = 60) -> list[Place]:
    """Named OSM features inside bbox=(west, south, east, north) whose name holds one of the sheet's distinctive words:
    nodes as points, ways as lines or areas (closed ways), relations as their bounding box."""
    words = distinctive_words(names)[:max_words]
    if not words:
        return []
    w, s, e, n = bbox
    rx = _overpass_regex(words)
    b = f"({s:.4f},{w:.4f},{n:.4f},{e:.4f})"
    q = (f'[out:json][timeout:180];(node["name"~"{rx}",i]{b};way["name"~"{rx}",i]{b};);out geom;'
         f'rel["name"~"{rx}",i]["boundary"!="administrative"]{b};out tags center bb;')
    key = hashlib.sha256(q.encode()).hexdigest()[:24]
    data = _get(OVERPASS, f"overpass/{key}.json", data=urllib.parse.urlencode({"data": q}).encode(), timeout=240)
    out = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        names_ = tuple(dict.fromkeys(v for k, v in tags.items() if k in NAME_KEYS or k.startswith("name:")))
        if not names_:
            continue
        kind = next((f"{k}={tags[k]}" for k in ("place", "natural", "waterway", "water", "landuse", "historic", "man_made",
                                                 "amenity", "leisure", "tourism", "railway", "highway") if k in tags), "other")
        if el["type"] == "node":
            out.append(Place(tags.get("name", names_[0]), names_, el["lon"], el["lat"], (el["lon"], el["lat"], el["lon"], el["lat"]), kind))
        elif el["type"] == "way" and el.get("geometry"):
            g = [(p["lon"], p["lat"]) for p in el["geometry"]]
            xs, ys = [p[0] for p in g], [p[1] for p in g]
            closed = len(g) >= 4 and g[0] == g[-1] and not kind.startswith(("waterway", "highway"))
            out.append(Place(tags.get("name", names_[0]), names_, float(np.mean(xs)), float(np.mean(ys)),
                             (min(xs), min(ys), max(xs), max(ys)), kind, tuple(g), closed))
        elif el["type"] == "relation" and el.get("bounds"):
            bb = el["bounds"]
            c = el.get("center", {"lon": (bb["minlon"] + bb["maxlon"]) / 2, "lat": (bb["minlat"] + bb["maxlat"]) / 2})
            ring = ((bb["minlon"], bb["minlat"]), (bb["maxlon"], bb["minlat"]), (bb["maxlon"], bb["maxlat"]), (bb["minlon"], bb["maxlat"]), (bb["minlon"], bb["minlat"]))
            out.append(Place(tags.get("name", names_[0]), names_, c["lon"], c["lat"], (bb["minlon"], bb["minlat"], bb["maxlon"], bb["maxlat"]),
                             kind, ring, True))
    return out


# -- OpenStreetMap vector tiles (the default for fitting) -----------------------------------------------------------
SOURCE = os.environ.get("GA_GAZETTEER_SOURCE", "tiles")         # "tiles" | "overpass"
TILE_LAYERS = ("place", "mountain_peak", "water_name", "waterway", "poi", "park", "transportation_name", "aerodrome_label")


def features_in_tiles(bbox, max_tiles: int = 600) -> list[Place]:
    """Every named feature in the OpenStreetMap vector tiles (OpenMapTiles schema, the pinned OpenFreeMap build the
    water check uses) covering bbox=(west, south, east, north): settlements, peaks, water names, waterways, points of
    interest, parks, road names. Zoom 14 (all detail) unless the box needs more than max_tiles tiles, then 13."""
    import mapbox_vector_tile
    from concurrent.futures import ThreadPoolExecutor
    from .primitives.basemap import _fetch_tile, _tile_range
    w, s, e, n = bbox
    for z in (14, 13, 12):
        xs, ys = _tile_range(s, w, n, e, z)
        if len(xs) * len(ys) <= max_tiles:
            break
    keys = [(x, y) for x in xs for y in ys]
    with ThreadPoolExecutor(8) as ex:
        blobs = list(ex.map(lambda k: _fetch_tile(z, *k), keys))
    N = 2 ** z
    out, seen = [], set()
    for (x, y), blob in zip(keys, blobs):
        if not blob:
            continue
        d = mapbox_vector_tile.decode(blob, default_options={"y_coord_down": True})
        for layer in TILE_LAYERS:
            L = d.get(layer)
            if not L:
                continue
            ext = L.get("extent", 4096)
            for f in L["features"]:
                pr = f["properties"]
                names_ = tuple(dict.fromkeys(v for k, v in pr.items() if (k == "name" or k.startswith("name:") or k.startswith("name_")) and isinstance(v, str) and v))
                if not names_:
                    continue
                g = f["geometry"]
                kind = f"{layer}={pr.get('class', '')}"
                parts, is_area = [], False
                if g["type"] == "Point":
                    parts = [[g["coordinates"]]]
                elif g["type"] == "MultiPoint":
                    parts = [[c] for c in g["coordinates"]]
                elif g["type"] == "LineString":
                    parts = [g["coordinates"]]
                elif g["type"] == "MultiLineString":
                    parts = g["coordinates"]
                elif g["type"] == "Polygon":
                    parts, is_area = [g["coordinates"][0]], True
                elif g["type"] == "MultiPolygon":
                    parts, is_area = [p[0] for p in g["coordinates"]], True
                for part in parts:
                    px = (x + np.asarray([c[0] for c in part], float) / ext) / N
                    py = (y + np.asarray([c[1] for c in part], float) / ext) / N
                    lon = px * 360 - 180
                    lat = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * py))))
                    nm = pr.get("name") or names_[0]
                    key = (nm, kind, tuple(np.round(lon, 4)), tuple(np.round(lat, 4)))   # tiles repeat their neighbours' labels
                    if key in seen:
                        continue
                    seen.add(key)
                    if len(part) == 1:
                        out.append(Place(nm, names_, float(lon[0]), float(lat[0]), (float(lon[0]), float(lat[0]), float(lon[0]), float(lat[0])), kind))
                    else:
                        out.append(Place(nm, names_, float(lon.mean()), float(lat.mean()), (float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max())),
                                         kind, tuple(zip(lon.tolist(), lat.tolist())), is_area and len(part) >= 4))
    return out


def features(bbox, names: list[str]) -> list[Place]:
    """Named features in bbox from the configured source (GA_GAZETTEER_SOURCE): pinned vector tiles, or live Overpass."""
    if SOURCE == "overpass":
        return features_in(bbox, names)
    return features_in_tiles(bbox)
