"""Reference vectors from a national open dataset on this machine, in the same form an Overpass answer has (ways with
tags and lon/lat geometry, place nodes), so every structure primitive can use either. Local first, network second
(knowledge: reference-overview): a mirror that times out must not end a route that the machine can serve itself.
Today the local store covers Great Britain (OS Open Zoomstack); elsewhere `available` is False and the caller goes
to Overpass."""
from __future__ import annotations

import os
import sqlite3

GPKG = os.environ.get("GA_LOCAL_VECTORS", "/data/reference/base-data/os_opendata/OS_Open_Zoomstack.gpkg")
GB_LONLAT = (-8.7, 49.8, 1.9, 60.9)

# local layer -> (Overpass-style tags by the layer's `type`, default tags)
LAYERS = {
    "rail": ({}, {"railway": "rail"}),
    "waterlines": ({"Local": {"waterway": "stream"}, "District": {"waterway": "stream"}, "MHW": {"natural": "coastline"}, "MLW": {"natural": "coastline"}}, {"waterway": "river"}),
    "roads_national": ({"Motorway": {"highway": "motorway"}}, {"highway": "primary"}),
    "roads_regional": ({"B Road": {"highway": "secondary"}}, {"highway": "primary"}),
    "roads_local": ({"Restricted": {"highway": "unclassified"}}, {"highway": "tertiary"}),
    "surfacewater": ({}, {"natural": "water"}),
}


def available(bbox_lonlat) -> bool:
    w, s, e, n = bbox_lonlat
    return os.path.exists(GPKG) and GB_LONLAT[0] <= w and e <= GB_LONLAT[2] and GB_LONLAT[1] <= s and n <= GB_LONLAT[3]


def fetch(bbox_lonlat, max_features: int = 200000) -> dict:
    """Ways and place nodes inside bbox=(west, south, east, north) in lon/lat, as {"elements": [...]} like Overpass."""
    from pyproj import Transformer
    from shapely import wkb
    to_bng = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
    to_ll = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
    w, s, e, n = bbox_lonlat
    xs, ys = to_bng.transform([w, e, w, e], [s, s, n, n])
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    con = sqlite3.connect(f"file:{GPKG}?mode=ro", uri=True)
    out = []

    def _geom(blob):
        flags = blob[3]; env = (flags >> 1) & 7
        return wkb.loads(bytes(blob[8 + {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}.get(env, 0):]))

    for layer, (by_type, default) in LAYERS.items():
        q = (f"SELECT t.geom, t.type FROM {layer} t JOIN rtree_{layer}_geom r ON t.id = r.id "
             "WHERE r.minx <= ? AND r.maxx >= ? AND r.miny <= ? AND r.maxy >= ?")
        for blob, typ in con.execute(q, (x1, x0, y1, y0)):
            try:
                g = _geom(blob)
            except Exception:                                   # noqa: BLE001
                continue
            tags = dict(by_type.get(typ, default))
            for part in getattr(g, "geoms", [g]):
                coords = list(part.exterior.coords) if part.geom_type == "Polygon" else list(part.coords)
                lon, lat = to_ll.transform([c[0] for c in coords], [c[1] for c in coords])
                out.append({"type": "way", "tags": tags, "geometry": [{"lon": a, "lat": b} for a, b in zip(lon, lat)]})
            if len(out) >= max_features:
                break
    q = ("SELECT t.geom, t.type, t.name1 FROM names t JOIN rtree_names_geom r ON t.id = r.id "
         "WHERE r.minx <= ? AND r.maxx >= ? AND r.miny <= ? AND r.maxy >= ? AND t.type IN ('City','Town','Village','Hamlet','Small Settlements','National Capital')")
    for blob, typ, name in con.execute(q, (x1, x0, y1, y0)):
        try:
            g = _geom(blob)
        except Exception:                                       # noqa: BLE001
            continue
        lon, lat = to_ll.transform(g.x, g.y)
        out.append({"type": "node", "lon": lon, "lat": lat, "tags": {"place": "village" if typ in ("Village", "Hamlet", "Small Settlements") else "town", "name": name}})
    return {"elements": out, "_bbox": [w, s, e, n], "_source": f"local:{os.path.basename(GPKG)}"}
