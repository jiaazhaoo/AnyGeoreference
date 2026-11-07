"""Primitives bound to the planning-drawing pipeline (e2e-plan-extract, s3_georef). Imported lazily: the library
lists them everywhere; they run only where that repository and its data (OS Open Names, the address register, the
OS Zoomstack roads) exist. Each wrapper turns the pipeline's return values into loop objects and nothing else.

Pipeline line format (what its label rules and fits expect): {"text", "conf", "x", "y", "h"} with the centre and
height in sheet pixels. A Cue carries a bbox; the two are converted here."""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np

from ..model import Candidate, Cue, Hypothesis
from . import Primitive, register
from evalcore import Evidence

E2E = os.environ.get("E2E_REPO", "/env/code/e2e-plan-extract")


def _e2e():
    if E2E not in sys.path:
        sys.path.insert(0, E2E)
    from e2e_plan_extract.s3_georef import labels, plan, gazetteer, grid_ticks, names_locate, abp_local   # noqa: E402
    return labels, plan, gazetteer, grid_ticks, names_locate, abp_local


def _on_sheet(c: Cue) -> bool:
    return not c.reader.endswith("_page")


def _line(c: Cue) -> dict:
    x0, y0, x1, y1 = c.bbox
    return {"text": c.text, "conf": c.confidence, "x": (x0 + x1) / 2, "y": (y0 + y1) / 2, "h": max(1.0, y1 - y0)}


def _cue(state, l: dict, kind: str, reader: str) -> Cue:
    return Cue(state.sheet.digest, kind, l.get("name") or l["text"], (l["x"] - l["h"], l["y"] - l["h"] / 2, l["x"] + l["h"], l["y"] + l["h"] / 2),
               reader, float(l.get("conf", 1.0)))


# -- readers ---------------------------------------------------------------------------------------------------------
def ocr_cached(state):
    """Cached page OCR (the pipeline's stageA ocr_top3.jsonl): the page named in the sheet's meta, boxes rescaled from
    the OCR's working size to the page's pixel size. $0, no GPU; the live OCR primitive is `ocr_words`."""
    path, page = state.sheet.meta.get("ocr_jsonl"), state.sheet.meta.get("page")
    if not path or not os.path.exists(path):
        return []
    out = []
    for line in open(path):
        r = json.loads(line)
        if page and r.get("image") != page:
            continue
        ow, oh = r.get("ocr_size") or (None, None)
        pw, ph = state.sheet.meta.get("page_size") or (state.sheet.meta.get("width"), state.sheet.meta.get("height"))
        sx, sy = (pw / ow, ph / oh) if (ow and pw) else (1.0, 1.0)
        crop = state.sheet.meta.get("crop_box")               # the sheet is a crop of the page: [x0, y0, x1, y1] in page px
        cx0, cy0 = (crop[0], crop[1]) if crop else (0.0, 0.0)
        for it in r["results"]:
            x0, y0, x1, y1 = it["bbox"]
            bx = (x0 * sx - cx0, y0 * sy - cy0, x1 * sx - cx0, y1 * sy - cy0)
            inside = (not crop) or (bx[0] >= -5 and bx[1] >= -5 and bx[2] <= crop[2] - crop[0] + 5 and bx[3] <= crop[3] - crop[1] + 5)
            # a word elsewhere on the page (title block, notes) still names streets and places for retrieval; only
            # words on the sheet itself may anchor a placement: the reader name tells the matchers apart
            out.append(Cue(state.sheet.digest, "text", it["text"].strip(), bx, "ocr_cached" if inside else "ocr_cached_page", float(it.get("confidence", 1.0))))
    return out


def ocr_words(state, maxside: int = 2600):
    labels, *_ = _e2e()
    out = []
    for l in labels.dedup(labels.ocr_all(state.sheet.image, maxside=maxside)):
        out.append(_cue(state, l, "text", "ocr_words"))
    return out


def road_and_place_labels(state):
    """Road / place / number cues from the text cues, by the pipeline's label rules."""
    _, plan, *_ = _e2e()
    import re
    out = []
    for on_sheet in (True, False):
        lines = [_line(c) for c in state.cues if c.kind == "text" and _on_sheet(c) == on_sheet]
        tag = "road_and_place_labels" if on_sheet else "road_and_place_labels_page"
        out += [_cue(state, lab, "road", tag) for lab in plan.road_labels(lines)]
        out += [_cue(state, lab, "place", tag) for lab in plan.place_labels(lines)]
        if on_sheet:
            out += [_cue(state, l, "number", tag) for l in lines if re.fullmatch(r"\d{1,3}[A-Za-z]?", l["text"])]
    return out


# -- retrieval -------------------------------------------------------------------------------------------------------
def _city(state):
    _, plan, _, _, names_locate, _ = _e2e()
    town_xy = tuple(state.sheet.meta.get("town_xy") or (435000.0, 387000.0))
    return names_locate.city_roads(town_xy, plan.roads_near), town_xy


def gazetteer_search(state, radius_m: float = 1500.0):
    """Record street + names read off the sheet -> an area from OS Open Names / the address register."""
    _, _, gazetteer, *_ = _e2e()
    city, town_xy = _city(state)
    address = state.sheet.record.get("address", "")
    phrases = gazetteer.phrases_of([c.text for c in state.cues if c.kind in ("road", "place", "text")])
    hit = gazetteer.locate(address, phrases, city, town_xy, state.sheet.meta.get("town", ""))
    if not hit:
        return []
    x, y, r = hit["x"], hit["y"], radius_m
    wkt = f"POLYGON(({x-r} {y-r},{x+r} {y-r},{x+r} {y+r},{x-r} {y+r},{x-r} {y-r}))"
    return [Candidate(state.sheet.digest, "gazetteer", wkt, "EPSG:27700", tuple(hit.get("hits", []))[:6], min(1.0, hit.get("cluster", 1) / 4),
                      note=f"street {hit.get('street')}")]


# -- matchers --------------------------------------------------------------------------------------------------------
def _sim6(T) -> tuple:
    """The pipeline's similarity (s, R, t) with w = s * (R @ [x, -y]) + t -> 6 affine coefficients."""
    s, R, t = float(T[0]), np.asarray(T[1], float), np.asarray(T[2], float)
    return (s * R[0, 0], -s * R[0, 1], t[0], s * R[1, 0], -s * R[1, 1], t[1])


def _footprint(state, T6) -> str:
    W, H = state.sheet.meta.get("width", 0), state.sheet.meta.get("height", 0)
    if not W or not H:
        return "POLYGON EMPTY"
    a, b, c, d, e, f = T6
    pts = [(a * x + b * y + c, d * x + e * y + f) for x, y in ((0, 0), (W, 0), (W, H), (0, H))]
    return "POLYGON((" + ",".join(f"{x:.2f} {y:.2f}" for x, y in pts) + f",{pts[0][0]:.2f} {pts[0][1]:.2f}))"


def grid_figures(state):
    """National-grid figures printed along the drawing's edges -> a similarity (the pipeline's grid_ticks.fit)."""
    _, _, _, grid_ticks, *_ = _e2e()
    lines = [_line(c) for c in state.cues if c.kind == "text" and _on_sheet(c)]
    near = None
    if state.candidates:
        import shapely.wkt
        g = shapely.wkt.loads(state.candidates[0].area_wkt); near = (g.centroid.x, g.centroid.y)
    r = grid_ticks.fit(lines, near)
    if not r:
        return []
    T6 = _sim6(r["T"])
    score = min(1.0, (r["n_e"] + r["n_n"]) / 8) * (1.0 / (1.0 + r["resid_m"] / 10))
    return [Hypothesis(state.sheet.digest, T6, _footprint(state, T6), "EPSG:27700", float(score), "grid_figures", (),
                       note=f"grid figures E{r['n_e']} N{r['n_n']}; resid {r['resid_m']:.1f} m; theta {r['theta']:.1f}; mpp {r['mpp']:.4f}")]


def text_anchor_fit(state, tol_m: float = 6.0, search_m: float = 16000.0):
    """House numbers x road names on the sheet -> address points from the local register -> RANSAC similarity."""
    labels, _, _, _, _, abp_local = _e2e()
    nums = [c for c in state.cues if c.kind == "number" and _on_sheet(c)]
    roads = sorted({c.text.upper() for c in state.cues if c.kind == "road"})      # road names from anywhere on the page
    if not nums or not roads:
        return []
    if state.candidates:
        import shapely.wkt
        x0, y0, x1, y1 = shapely.wkt.loads(state.candidates[0].area_wkt).bounds
        bbox = (x0 - 500, y0 - 500, x1 + 500, y1 + 500)
    else:
        tx, ty = tuple(state.sheet.meta.get("town_xy") or (435000.0, 387000.0))
        bbox = (tx - search_m, ty - search_m, tx + search_m, ty + search_m)
    anchors = []
    import re
    for n in nums:
        for road in roads:
            for r in abp_local.find(f"{n.text} {road.title()}", bbox, limit=10):
                if (r.get("BUILDING_NUMBER") or "").upper() == n.text.upper() and \
                        re.sub(r"[^A-Z ]", "", (r.get("THOROUGHFARE_NAME") or "").upper()) == road:
                    l = _line(n)
                    anchors.append({"label": f"{n.text} {road}", "px": (l["x"], l["y"]), "bng": (r["X_COORDINATE"], r["Y_COORDINATE"]), "addr": r["ADDRESS"]})
                    break
    if len(anchors) < 3:
        return []
    r = labels.ransac(anchors, tol_m=tol_m)
    if not r:
        return []
    # a degenerate fit (anchors that collapse to one point give scale 0) is not a placement; plausible metres per
    # pixel for a scanned drawing lie between 2 mm and 2 m (one graded drawing: 4/10 inliers, mpp 0.0, 92 m off)
    if not (0.002 <= float(r.get("m_per_px") or 0) <= 2.0):
        return []
    T6 = _sim6(r["T"])
    return [Hypothesis(state.sheet.digest, T6, _footprint(state, T6), "EPSG:27700", float(len(r["inliers"]) / r["n_anchors"]), "text_anchor_fit",
                       (0,) if state.candidates else (), note=f"inliers {len(r['inliers'])}/{r['n_anchors']}; rms {r['rms_m']} m; mpp {r['m_per_px']}; rot {r['rotation_deg']}")]


# -- verification ----------------------------------------------------------------------------------------------------
def address_in_footprint(state):
    """The record's address, found in the local register, lies inside the best hypothesis' footprint; and how far it
    is from the footprint centre. Independent of every reader: the address register is its own family."""
    *_, abp_local = _e2e()
    if not state.hypotheses:
        return []
    import shapely.wkt
    fp = shapely.wkt.loads(state.hypotheses[0].site_wkt)
    if fp.is_empty:
        return []
    cx, cy = fp.centroid.x, fp.centroid.y
    hits = abp_local.find(state.sheet.record.get("address", ""), (cx - 5000, cy - 5000, cx + 5000, cy + 5000), limit=1)
    if not hits:
        return [Evidence("address_in_footprint", None, "deterministic", "record-text", note="address not found near the footprint")]
    from shapely.geometry import Point
    p = Point(hits[0]["X_COORDINATE"], hits[0]["Y_COORDINATE"])
    return [Evidence("address_in_footprint", bool(fp.contains(p)), "deterministic", "record-text", note=hits[0]["ADDRESS"][:80]),
            Evidence("address_to_centre_m", float(p.distance(fp.centroid)), "deterministic", "address-register")]


for p in (
    Primitive("ocr_cached", "sheet-reader", True, (), "cue", "cached page OCR from the pipeline's stageA (no GPU)", ocr_cached, "plans_gb"),
    Primitive("ocr_words", "sheet-reader", True, (), "cue", "OCR every word on the sheet with its pixel box", ocr_words, "plans_gb", requires=("e2e-plan-extract", "paddleocr")),
    Primitive("road_and_place_labels", "sheet-reader", True, ("cue",), "cue", "road / place / number cues from OCR text by the pipeline's label rules", road_and_place_labels, "plans_gb", requires=("e2e-plan-extract",)),
    Primitive("vlm_read_names", "sheet-reader", False, (), "cue", "a vision model reads road names and numbers (hosted; cached)", None, "plans_gb", cost_estimate=0.01, requires=("e2e-plan-extract", "OPENROUTER_API_KEY")),
    Primitive("gazetteer_search", "gazetteer", True, ("cue",), "candidate", "record street + sheet names -> an area from Open Names / the address register", gazetteer_search, "plans_gb", requires=("e2e-plan-extract", "OS Open Names", "OS Zoomstack")),
    Primitive("grid_figures", "geometry", True, ("cue",), "hypothesis", "national-grid figures along the edges -> similarity", grid_figures, "plans_gb", requires=("e2e-plan-extract",)),
    Primitive("text_anchor_fit", "geometry", True, ("cue",), "hypothesis", "house numbers x road names vs the local address register -> RANSAC similarity", text_anchor_fit, "plans_gb", requires=("e2e-plan-extract", "AddressBase Premium")),
    Primitive("address_in_footprint", "address-register", True, ("hypothesis",), "evidence", "the record's address point inside the best footprint; distance to its centre", address_in_footprint, "plans_gb", requires=("e2e-plan-extract", "AddressBase Premium")),
    Primitive("snap_faces", "geometry", True, ("hypothesis",), "evidence", "site polygon vs OS map faces (declared; the pipeline's step 13)", None, "plans_gb", requires=("e2e-plan-extract", "OS base map")),
):
    register(p)


# -- place lookup (asked for by the main agent on blind inputs) -----------------------------------------------------
_ABBR = {"st": "Street", "st.": "Street", "rd": "Road", "rd.": "Road", "la": "Lane", "la.": "Lane", "ln": "Lane", "ave": "Avenue", "pl": "Place",
         "sq": "Square", "ter": "Terrace", "gdns": "Gardens", "cres": "Crescent", "br": "Bridge", "br.": "Bridge", "gt": "Great", "upr": "Upper", "lr": "Lower"}


def name_variants(text: str) -> list[str]:
    """The ways a printed label may be spelt in the names set: as read, abbreviations expanded, title case, 'St' as Saint."""
    t = " ".join(text.strip().split())
    words = [w for w in t.replace(",", " ").split(" ") if w]
    exp = [(_ABBR.get(w.lower(), w)) for w in words]
    out = [t, " ".join(exp), " ".join(exp).title(), t.title()]
    if exp and exp[0].lower().rstrip(".") == "st" or (exp and exp[0] == "Street"):
        out.append(" ".join(["St"] + words[1:]).title())
    return list(dict.fromkeys(x for x in out if x))


def place_lookup(state, radius_m: float = 1500.0, kinds=("place", "landmark", "road"), max_names: int = 12):
    """Place and landmark names read off the sheet -> OS Open Names -> one candidate area: the cluster of hits that
    sit closest together (the sheet's names belong to one place; homonyms elsewhere in Britain do not cluster).
    Radius grows with the kind of place found (a city needs more than a hamlet)."""
    import sqlite3
    import numpy as np
    db = os.environ.get("E2E_OPEN_NAMES", "/data/reference/base-data/opname_csv_gb/os_open_names_uk.sqlite")
    names = []
    for c in state.cues:
        if c.kind in kinds and len(c.text.strip()) >= 4:
            names.append(c.text.strip())
    names = list(dict.fromkeys(names))[:max_names]
    if not names:
        return []
    con = sqlite3.connect(db)
    hits = []
    for n in names:
        seen = 0
        for v in name_variants(n):
            for r in con.execute("SELECT NAME1, TYPE, LOCAL_TYPE, GEOMETRY_X, GEOMETRY_Y FROM open_names WHERE NAME1 = ? COLLATE NOCASE LIMIT 20", (v,)):
                hits.append((n, r[1], r[2], float(r[3]), float(r[4]))); seen += 1
            if seen:
                break
    if not hits:
        state.evidence.append(Evidence("place_lookup_miss", names[:6], "record", "gazetteer"))
        return []
    P = np.array([[h[3], h[4]] for h in hits])
    # the densest cluster: for each hit, how many distinct names fall within 5 km; keep the best hit's neighbourhood
    best, best_n = None, -1
    for i, h in enumerate(hits):
        d = np.hypot(*(P - P[i]).T)
        n_names = len({hits[j][0] for j in np.nonzero(d <= 5000)[0]})
        if n_names > best_n:
            best, best_n = i, n_names
    core = [hits[j] for j in np.nonzero(np.hypot(*(P - P[best]).T) <= 5000)[0]]
    cx, cy = float(np.mean([h[3] for h in core])), float(np.mean([h[4] for h in core]))
    big = any(h[2] in ("City", "Town") for h in core)
    r = max(radius_m, 4000.0 if big else radius_m, float(np.max(np.hypot(*(np.array([[h[3], h[4]] for h in core]) - [cx, cy]).T))) + 500)
    wkt = f"POLYGON(({cx-r} {cy-r},{cx+r} {cy-r},{cx+r} {cy+r},{cx-r} {cy+r},{cx-r} {cy-r}))"
    return [Candidate(state.sheet.digest, "gazetteer", wkt, "EPSG:27700", tuple(sorted({h[0] for h in core})), min(1.0, best_n / 4),
                      note=f"{best_n} names cluster within 5 km; radius {r:.0f} m; types {sorted({h[2] for h in core})[:4]}")]


# -- road names as geometry: locate by junctions, fit labels onto their named roads ---------------------------------
def _road_labels(state):
    out = []
    for c in state.cues:
        if c.kind == "road" and len(c.text.strip()) >= 3:
            x0, y0, x1, y1 = c.bbox
            out.append({"name": c.text.strip().upper(), "text": c.text, "x": (x0 + x1) / 2, "y": (y0 + y1) / 2, "h": max(1.0, y1 - y0), "angle": 0.0,
                        "conf": c.confidence})
    return out


def _town_xy(state):
    """The area to search: the first candidate; else the record's town hint; else the densest cluster of the sheet's
    own names (roads, places, landmarks) in the national names set, which is appended as a candidate so the trace
    shows it. A fixed default town would make a generic system silently local."""
    import shapely.wkt
    if state.candidates:
        g = shapely.wkt.loads(state.candidates[0].area_wkt).centroid
        return (g.x, g.y)
    if state.sheet.meta.get("town_xy"):
        return tuple(state.sheet.meta["town_xy"])
    found = place_lookup(state, kinds=("place", "landmark", "road"), max_names=24)
    if found:
        state.add("candidate", found)
        g = shapely.wkt.loads(found[0].area_wkt).centroid
        return (g.x, g.y)
    return None


def road_junction_locate(state, search_m: float = 16000.0, radius_m: float = 1200.0):
    """Where the sheet's named roads meet: every pair of names read off the sheet that are roads of the area and
    meet within 150 m votes for a point; the densest cluster of votes is the candidate (the pipeline's names_locate).
    Needs at least two road names; the area to search comes from the first candidate (a place lookup) or the meta."""
    _, plan, _, _, names_locate, _ = _e2e()
    labs = _road_labels(state)
    if len(labs) < 2:
        return []
    town = _town_xy(state)
    if town is None:
        state.evidence.append(Evidence("no_search_area", len(labs), "deterministic", "road-network", note="no candidate, no town hint, names cluster nowhere"))
        return []
    city = names_locate.city_roads(town, plan.roads_near, r=search_m)
    names = names_locate.city_names([l["name"] for l in labs], city)
    if len(names) < 2:
        state.evidence.append(Evidence("road_names_in_area", len(names), "deterministic", "road-network", note=f"of {len(labs)} read"))
        return []
    r = names_locate.locate(sorted(names), city, junction_m=150.0, min_pairs=1)
    if not r:
        return []
    x, y, rad = r["x"], r["y"], radius_m
    wkt = f"POLYGON(({x-rad} {y-rad},{x+rad} {y-rad},{x+rad} {y+rad},{x-rad} {y+rad},{x-rad} {y-rad}))"
    return [Candidate(state.sheet.digest, "road-network", wkt, "EPSG:27700", tuple(sorted(names))[:12], min(1.0, r["pairs"] / 6),
                      note=f"{r['pairs']} name pairs meet here, {r['rival_pairs']} elsewhere; {len(names)} of {len(labs)} names are roads of the area")]


def road_name_fit(state, theta_step: float = 5.0, inlier_m: float = 60.0, min_inliers: int = 4, search_m: float = 2500.0,
                  res_m: float = 5.0, t_step_m: float = 40.0, scales=None):
    """Similarity (scale, rotation, translation) that puts every road label on its named road. Labels are assigned
    to roads by the pipeline's fuzzy name match; each matched road is rasterised and distance-transformed over the
    candidate area, so a pose is scored by a vectorised lookup: every rotation (theta_step) x scale x translation
    on a grid (t_step_m) in one numpy pass, score = labels within inlier_m of their own road. The best pose is then
    refined by point-to-line ICP on its inliers. No label angles needed: works on a model's reading as on OCR."""
    import math
    import cv2
    import numpy as np
    from shapely.geometry import Point
    from shapely.ops import nearest_points
    _, plan, *_ = _e2e()
    labs = _road_labels(state)
    if len(labs) < 3:
        return []
    near = _town_xy(state)
    if near is None:
        return []
    roads = plan.roads_near(near[0], near[1], r=search_m)
    if not roads:
        return []
    matched, _keep = plan.match_roads(labs, roads, near)
    if len(matched) < 3:
        state.evidence.append(Evidence("road_labels_matched", len(matched), "deterministic", "road-network", note=f"of {len(labs)}"))
        return []
    W, H = state.sheet.meta.get("width", 0) or 1, state.sheet.meta.get("height", 0) or 1
    # distance rasters, one per matched road, over the search square
    x0, y0 = near[0] - search_m, near[1] - search_m
    n = int(2 * search_m / res_m)
    dist = {}
    for name in {m["road"] for m in matched}:
        img = np.zeros((n, n), np.uint8)
        g = roads[name]
        for part in getattr(g, "geoms", [g]):
            c = np.asarray(part.coords, float)
            px = np.c_[(c[:, 0] - x0) / res_m, (n - 1) - (c[:, 1] - y0) / res_m].round().astype(np.int32)
            cv2.polylines(img, [px], False, 255, 1)
        dist[name] = cv2.distanceTransform((img == 0).astype(np.uint8), cv2.DIST_L2, 3) * res_m
    D = np.stack([dist[m["road"]] for m in matched])                      # (L, n, n)
    P = np.array([[m["x"], -m["y"]] for m in matched], float)             # y up
    P -= P.mean(0)
    L = len(matched)
    scales = np.asarray(scales if scales else np.geomspace(0.02, 40.0, 60), float)
    tg = np.arange(-search_m + 200, search_m - 200, t_step_m)
    TX, TY = np.meshgrid(tg, tg); T = np.c_[TX.ravel(), TY.ravel()] + np.array(near)   # candidate centres of the label cloud
    best = None
    for th in np.arange(0.0, 360.0, theta_step):
        R = np.array([[math.cos(math.radians(th)), -math.sin(math.radians(th))], [math.sin(math.radians(th)), math.cos(math.radians(th))]])
        RP = (R @ P.T).T                                                   # (L, 2)
        for s_ in scales:
            X = s_ * RP                                                    # label offsets from the cloud centre, metres
            pos = T[:, None, :] + X[None, :, :]                            # (Tn, L, 2)
            ix = ((pos[..., 0] - x0) / res_m).round().astype(np.int64)
            iy = ((n - 1) - (pos[..., 1] - y0) / res_m).round().astype(np.int64)
            ok = (ix >= 0) & (ix < n) & (iy >= 0) & (iy < n)
            ix = np.clip(ix, 0, n - 1); iy = np.clip(iy, 0, n - 1)
            d = D[np.arange(L)[None, :], iy, ix]                           # (Tn, L)
            d = np.where(ok, d, 1e9)
            inl = (d <= inlier_m).sum(1)
            k = int(np.argmax(inl))
            if best is None or (inl[k], -float(np.median(d[k]))) > best[0]:
                best = ((int(inl[k]), -float(np.median(d[k]))), th, s_, T[k].copy(), d[k].copy())
    if best is None or best[0][0] < min_inliers:
        state.evidence.append(Evidence("road_fit_inliers", best[0][0] if best else 0, "deterministic", "road-network", note=f"of {L} matched labels"))
        return []
    (n_in, _), th, s_, t, d = best
    R = np.array([[math.cos(math.radians(th)), -math.sin(math.radians(th))], [math.sin(math.radians(th)), math.cos(math.radians(th))]])
    geoms = [roads[m["road"]] for m in matched]
    inl = d <= inlier_m
    X = s_ * (R @ P[inl].T).T
    G_in = [g for g, k in zip(geoms, inl) if k]
    for _ in range(6):                                                     # ICP refine on the inliers
        Q = np.array([np.array(nearest_points(g, Point(*(x + t)))[0].coords[0]) for g, x in zip(G_in, X)])
        t = t + (Q - (X + t)).mean(0)
    d2 = np.array([g.distance(Point(*(s_ * (R @ p) + t))) for g, p in zip(geoms, P)])
    n_in = int((d2 <= inlier_m).sum())
    # sheet px -> BNG: w = s R ([x, -y] - mean) + t
    mean_px = np.array([[m["x"], -m["y"]] for m in matched], float).mean(0)
    a, b = s_ * R[0, 0], -s_ * R[0, 1]; dd, e = s_ * R[1, 0], -s_ * R[1, 1]
    c_ = t[0] - (a * mean_px[0] + b * (-mean_px[1])); f = t[1] - (dd * mean_px[0] + e * (-mean_px[1]))
    T6 = (a, b, c_, dd, e, f)
    pts = [(a * x + b * y + c_, dd * x + e * y + f) for x, y in ((0, 0), (W, 0), (W, H), (0, H))]
    wkt = "POLYGON((" + ",".join(f"{x:.2f} {y:.2f}" for x, y in pts) + f",{pts[0][0]:.2f} {pts[0][1]:.2f}))"
    return [Hypothesis(state.sheet.digest, T6, wkt, "EPSG:27700", float(n_in / L), "road_name_fit", (0,) if state.candidates else (),
                       note=f"{n_in}/{L} labels on their roads (<= {inlier_m:.0f} m); median {np.median(d2):.0f} m; theta {th:.0f}; mpp {s_:.3f}; roads {len(set(dist))}")]


register(Primitive("road_junction_locate", "road-network", True, ("cue",), "candidate",
                   "where the sheet's named roads meet in the road network: the densest cluster of junction votes as the candidate area", road_junction_locate, "plans_gb", requires=("e2e-plan-extract", "OS Zoomstack")))
register(Primitive("road_name_fit", "geometry", True, ("cue",), "hypothesis",
                   "similarity that puts every road label on its named road centreline (rotation x scale sweep, point-to-line ICP); no label angles needed", road_name_fit, "plans_gb", requires=("e2e-plan-extract", "OS Zoomstack")))


def places_in_footprint(state, kinds=("place", "landmark"), max_names: int = 20):
    """Place and landmark names read off the sheet, looked up in OS Open Names (populated places and landforms,
    not roads): how many of them fall inside the best hypothesis' footprint. Independent of the road geometry the
    road-name fit used, so it is the second family for a street map."""
    import sqlite3
    import shapely.wkt
    from shapely.geometry import Point
    if not state.hypotheses:
        return []
    fp = shapely.wkt.loads(state.hypotheses[0].site_wkt)
    if fp.is_empty:
        return []
    db = os.environ.get("E2E_OPEN_NAMES", "/data/reference/base-data/opname_csv_gb/os_open_names_uk.sqlite")
    names = list(dict.fromkeys(c.text.strip() for c in state.cues if c.kind in kinds and len(c.text.strip()) >= 4))[:max_names]
    if not names:
        return [Evidence("places_in_footprint", None, "deterministic", "gazetteer", note="no place names read")]
    con = sqlite3.connect(db)
    grown = fp.buffer(max(200.0, 0.1 * math.sqrt(fp.area)))
    inside, found = [], 0
    for nme in names:
        rows = con.execute("SELECT GEOMETRY_X, GEOMETRY_Y FROM open_names WHERE NAME1 = ? COLLATE NOCASE AND TYPE IN ('populatedPlace','landform','landcover','hydrography','other') LIMIT 50", (nme,)).fetchall()
        if not rows:
            continue
        found += 1
        if any(grown.contains(Point(float(x), float(y))) for x, y in rows):
            inside.append(nme)
    return [Evidence("places_in_footprint", len(inside), "deterministic", "gazetteer", note=f"{len(inside)} of {found} found names inside: {inside[:6]}"),
            Evidence("places_found", found, "deterministic", "gazetteer")]


register(Primitive("places_in_footprint", "gazetteer", True, ("hypothesis", "cue"), "evidence",
                   "place / landmark names on the sheet found in Open Names inside the footprint (a family independent of road geometry)", places_in_footprint, "plans_gb", requires=("OS Open Names",)))


register(Primitive("place_lookup", "gazetteer", True, ("cue",), "candidate",
                   "place / landmark / road names on the sheet -> OS Open Names -> the densest cluster as one candidate area", place_lookup, "plans_gb", requires=("OS Open Names",)))

# -- the production pipeline's learned matcher -------------------------------------------------------------------
def plan_minima_match(state, sigma_m: float = 250.0, windows: int = 40, deadline_s: float = 180.0, thetas=None, min_score: float = 15.0):
    """MINIMA (LoFTR) sliding-window match of the drawing against OS base-map tiles around the candidate area: the
    pipeline's own learned matcher (s3_georef.plan.minima). Seed = the first candidate's centre; rotation candidates
    from the north-arrow cue when one was read, else the four uprights; scale from a scale cue when one was read,
    else the pipeline's sweep. The council's OS WFS extract comes from the sheet meta (`gazetteer gpkg_wfs`)."""
    import math
    import cv2
    _, plan, *_ = _e2e()
    sys.path.insert(0, E2E)
    from e2e_plan_extract.s3_georef import batch as _b
    if not state.candidates:
        return []
    wfs = state.sheet.meta.get("gpkg_wfs")
    if wfs:
        plan.WFS = wfs
    import shapely.wkt
    c = shapely.wkt.loads(state.candidates[0].area_wkt).centroid
    img = cv2.imread(state.sheet.image)
    if img is None:
        raise FileNotFoundError(state.sheet.image)
    H, W = img.shape[:2]
    mask = np.full((H, W), 255, np.uint8)
    # rotation candidates: a read north arrow first, then the uprights
    th = list(thetas) if thetas else []
    for cue in state.cues:
        if cue.kind == "arrow":
            txt = cue.text.lower()
            m = re.search(r"(-?\d+(?:\.\d+)?)\s*deg", txt)
            if m:
                th.append(float(m.group(1)) % 360)
            elif "up" in txt or txt.strip() in ("n", "north"):
                th.append(0.0)
    th = th + [t for t in (0.0, 90.0, 180.0, 270.0) if all(abs((t - u + 180) % 360 - 180) > 15 for u in th)]
    # scale: "1:1250" or "1/500" on the sheet -> metres per pixel at the pipeline's nominal 200 dpi
    mpp = None
    for cue in state.cues:
        if cue.kind == "scale":
            m = re.search(r"1\s*[:/]\s*(\d{3,5})", cue.text)
            if m:
                mpp = int(m.group(1)) * 25.4 / 200 / 1000
                break
    import time
    matcher = _MINIMA.setdefault("m", plan.load_minima())
    r = plan.minima(matcher, img, mask, (c.x, c.y), th, sigma=sigma_m, mpp=mpp, stop_at=None, single_zoom=bool(mpp),
                    deadline=time.time() + deadline_s, windows=windows)
    if not r or not r.get("geojson") or float(r.get("score") or 0) < min_score:
        return []
    fp = plan.geo_to_bng(r["geojson"])
    T = _b.transform_from_footprint(fp, W, H, r["theta"])
    T6 = _sim6(T)
    return [Hypothesis(state.sheet.digest, T6, fp.wkt, "EPSG:27700", min(1.0, float(r["score"]) / 100.0), "plan_minima_match", (0,),
                       note=f"minima score {r['score']} V {r.get('V')} Q {r.get('Q')}; theta {r['theta']}; scale {r['scale']}; mpp_hint {mpp}; thetas {th[:4]}")]


_MINIMA: dict = {}
import re  # noqa: E402

register(Primitive("plan_minima_match", "basemap", True, ("candidate",), "hypothesis",
                   "the pipeline's learned matcher: MINIMA sliding-window match of the drawing against OS base-map tiles round the candidate area",
                   plan_minima_match, "plans_gb", requires=("e2e-plan-extract", "GeoPlanAgent + MINIMA weights", "council OS WFS extract", "torch")))
