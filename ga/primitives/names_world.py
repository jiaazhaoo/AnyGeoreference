"""Names as geometry, anywhere: a sheet with no coordinates, no graticule and no corner values is placed by the names
printed on it, against the world gazetteer (ga.gazetteer, OpenStreetMap fetched per sheet), then moved onto the ground
by its water.

  name_search_area   cues -> candidate areas. Every name read is searched (Nominatim), worldwide or inside the area
                     the record's hint names; the places where the most DIFFERENT names occur close together become
                     the candidates: homonyms are scattered, a sheet's names are not.
  name_fit           cues + candidates -> one hypothesis. Inside each candidate area, the named features of the pinned
                     OpenStreetMap vector tiles and the search's own answers; every two named points on the sheet
                     paired with two features propose a similarity (scale, small rotation, shift; the y axis flipped,
                     sheet pixels run down); the proposal that puts the most other names on a feature of the same name
                     wins and is refined on those names (nearest point of a line, inside of an area). Facts: how many
                     different gazetteer names agree, and how many any placement elsewhere gets (chance).
  water_refine       the names placement against OpenStreetMap's water: whole-sheet shifts until close, then the
                     quadrants that agree fit scale and rotation. Facts: does the whole sheet lock, do the quadrants.

A placement from names alone is as good as the label positions: a label sits beside its feature, so the error is
about a label's length on the ground (250-700 m on a 1:62,500 sheet). The water brings it to tens of metres where
the sheet prints water and OSM maps it; only then may the policy accept."""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

from ..model import Candidate, Hypothesis
from . import Primitive, register
from evalcore import Evidence

NAME_KINDS = ("place", "landmark", "road", "text")


def _names(state, kinds=NAME_KINDS, min_len: int = 3) -> list[tuple[str, float, float]]:
    """(text, x, y) of every name label: words only (digits and spot heights dropped), each reading kept apart."""
    import re
    out = []
    for c in state.cues:
        if c.kind not in kinds:
            continue
        t = " ".join(w for w in re.split(r"\s+", c.text.strip()) if not any(ch.isdigit() for ch in w))
        if sum(ch.isalpha() for ch in t) < min_len:
            continue
        # a name has a written-out word of four letters or more, or two words ("Mt Carmel", "Hog Br"): an article
        # ("der"), a lone abbreviation ("Fabr.") or a lone short word names nothing in particular
        words = re.findall(r"[^\W\d_]+\.?", t)
        if len(words) < 2 and not any(len(w) >= 4 and not w.endswith(".") for w in words):
            continue
        x0, y0, x1, y1 = c.bbox
        out.append((t, (x0 + x1) / 2.0, (y0 + y1) / 2.0))
    return out


def _utm(lon: float, lat: float) -> str:
    return f"EPSG:{(32600 if lat >= 0 else 32700) + int((lon + 180) // 6) + 1}"


def _box_wkt(b) -> str:
    w, s, e, n = b
    return f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))"


# -- area ---------------------------------------------------------------------------------------------------------
def name_search_area(state, cluster_m: float = 25000.0, margin_m: float = 8000.0, max_extent_m: float = 30000.0,
                     limit: int = 40, max_names: int = 40, keep: int = 3):
    """Candidate areas (EPSG:4326 boxes) for the sheet: where the sheet's different names cluster in the gazetteer,
    searched worldwide, or inside the area the record's hint names (a region; country around a named town)."""
    from .. import gazetteer as gz
    hint = (state.sheet.record.get("hint") or "").strip()
    area = gz.area_of(hint) if hint else None
    names = list(dict.fromkeys(t for t, _, _ in _names(state)))[:max_names]
    if not names:
        return []
    hits, saturated = [], []
    for nm in names:
        res = gz.search(nm, area=area, limit=limit)
        if len(res) >= limit:                            # a name found everywhere says nothing about where
            saturated.append(nm); continue
        for p in res:
            if gz.matches(nm, p) and p.extent_m() <= max_extent_m:
                hits.append((nm, p.lon, p.lat))
    state.evidence.append(Evidence("names_searched", len(names), "deterministic", "gazetteer",
                                   note=f"{len({h[0] for h in hits})} found, {len(saturated)} too common; area {'hint ' + hint if area else 'world'}"))
    if not hits:
        return []
    P = np.array([[h[1], h[2]] for h in hits])
    lat0 = np.radians(P[:, 1])
    out, used = [], np.zeros(len(hits), bool)
    for _ in range(keep):
        best, best_n, best_idx = None, 0, None
        for i in range(len(hits)):
            if used[i]:
                continue
            d = np.hypot((P[:, 0] - P[i, 0]) * 111320 * np.cos(lat0[i]), (P[:, 1] - P[i, 1]) * 110574)
            idx = np.nonzero((d <= cluster_m) & ~used)[0]
            n = len({hits[j][0] for j in idx})
            if n > best_n:
                best, best_n, best_idx = i, n, idx
        if best is None or best_n < 2:
            break
        used[best_idx] = True
        cx, cy = P[best_idx].mean(axis=0)
        dlat = margin_m / 110574
        dlon = margin_m / (111320 * math.cos(math.radians(cy)))
        box = (P[best_idx, 0].min() - dlon, P[best_idx, 1].min() - dlat, P[best_idx, 0].max() + dlon, P[best_idx, 1].max() + dlat)
        names_in = tuple(sorted({hits[j][0] for j in best_idx}))
        out.append(Candidate(state.sheet.digest, "gazetteer", _box_wkt(box), "EPSG:4326", names_in, min(1.0, best_n / 6),
                             note=f"{best_n} different names within {cluster_m / 1000:.0f} km: {list(names_in)[:6]}"))
    return out


# -- fit ----------------------------------------------------------------------------------------------------------
def _shape_xy(p, to_xy, max_pts: int = 60) -> tuple[np.ndarray, bool]:
    if p.shape:
        g = np.asarray(p.shape, float)
        if len(g) > max_pts:
            g = g[np.linspace(0, len(g) - 1, max_pts).astype(int)]
        x, y = to_xy.transform(g[:, 0], g[:, 1])
        return np.c_[x, y], p.area
    x, y = to_xy.transform([p.lon], [p.lat])
    return np.c_[x, y], False


def _flip(xy: np.ndarray) -> np.ndarray:
    return xy[:, 0] - 1j * xy[:, 1]                       # sheet pixels (y down) as complex numbers, north up


def name_fit(state, tol_frac: float = 0.03, max_rot_deg: float = 15.0, scale_range=(0.2, 200.0), min_sep_frac: float = 0.08,
             max_seed_cands: int = 6, point_extent_m: float = 400.0, iters: int = 6, top_seeds: int = 300):
    """The similarity that puts the most different sheet names on gazetteer features of the same name, in each
    candidate area; the best area's placement is the hypothesis (UTM of its centre). tol_frac: how far (as a share
    of the sheet's diagonal) a label may sit from its feature; max_rot_deg: maps are drawn north up within this."""
    import shapely.wkt
    from pyproj import Transformer
    from shapely.geometry import Point, Polygon
    from .. import gazetteer as gz
    obs = _names(state)
    W, H = state.sheet.meta.get("width", 0), state.sheet.meta.get("height", 0)
    if len(obs) < 3 or not W or not H or not state.candidates:
        return []
    diag = math.hypot(W, H)
    tol_px = tol_frac * diag
    texts = list(dict.fromkeys(t for t, _, _ in obs))
    results, alts = [], []                              # alts: every refined seed, (names, centre lon, lat, ground diagonal)
    for ci, cand in enumerate(state.candidates[:3]):
        if ci and cand.source == "gazetteer" and len(cand.answers) < 3:     # two names close together: chance
            continue
        box = shapely.wkt.loads(cand.area_wkt).bounds
        feats = gz.features(box, texts)
        # the name search's own answers inside the box are gazetteer entries too (cached: no new request)
        hint = (state.sheet.record.get("hint") or "").strip()
        area = gz.area_of(hint) if hint else None
        for t in texts[:40]:
            feats += [p for p in gz.search(t, area=area) if box[0] <= p.lon <= box[2] and box[1] <= p.lat <= box[3]]
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        crs = _utm(cx, cy)
        to_xy = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        # each observation's gazetteer candidates as vertex arrays in metres
        cands = []                                      # per obs: list of (xy array, is_area, polygon or None, point-like)
        for t, _, _ in obs:
            lst = []
            for p in feats:
                if gz.matches(t, p):
                    xy, is_area = _shape_xy(p, to_xy)
                    pointlike = p.extent_m() <= point_extent_m
                    if pointlike and any(c[3] and np.hypot(*(c[0].mean(axis=0) - xy.mean(axis=0))) < 150 for c in lst):
                        continue                        # the same feature from two sources, or twice
                    lst.append((xy, is_area, Polygon(xy) if is_area and len(xy) >= 4 else None, pointlike, gz.fold(p.name)))
            cands.append(lst)
        found = [i for i, c in enumerate(cands) if c]
        if len({obs[i][0] for i in found}) < 3:
            results.append({"ci": ci, "n": len({obs[i][0] for i in found}), "found": len(found)})
            continue
        sheet = _flip(np.array([[o[1], o[2]] for o in obs]))
        # seeds: two observations, each with a point-like candidate
        seeds_obs = [i for i in found if 0 < sum(c[3] for c in cands[i]) <= max_seed_cands]
        pts = {i: [c[0].mean(axis=0) for c in cands[i] if c[3]] for i in seeds_obs}
        A, B, PA, PB = [], [], [], []
        for a_i in range(len(seeds_obs)):
            for b_i in range(a_i + 1, len(seeds_obs)):
                i, j = seeds_obs[a_i], seeds_obs[b_i]
                if obs[i][0] == obs[j][0] or abs(sheet[i] - sheet[j]) < min_sep_frac * diag:
                    continue
                for qa in pts[i]:
                    for qb in pts[j]:
                        A.append(i); B.append(j); PA.append(qa[0] + 1j * qa[1]); PB.append(qb[0] + 1j * qb[1])
        if not A:
            results.append({"ci": ci, "n": len({obs[i][0] for i in found}), "found": len(found), "seeds": 0})
            continue
        A, B, PA, PB = np.array(A), np.array(B), np.array(PA), np.array(PB)
        m = (PB - PA) / (sheet[B] - sheet[A])
        t = PA - m * sheet[A]
        ok = (np.abs(np.degrees(np.angle(m))) <= max_rot_deg) & (np.abs(m) >= scale_range[0]) & (np.abs(m) <= scale_range[1])
        m, t, A, B = m[ok], t[ok], A[ok], B[ok]
        if not len(m):
            results.append({"ci": ci, "n": len({obs[i][0] for i in found}), "found": len(found), "seeds": 0})
            continue
        # quick score on point-like candidates, then the full score on the best seeds
        pidx, pxy = [], []
        for i in found:
            for c in cands[i]:
                if c[3]:
                    pidx.append(i); pxy.append(c[0].mean(axis=0))
        pidx, pz = np.array(pidx), np.array([q[0] + 1j * q[1] for q in pxy])
        pred = m[:, None] * sheet[pidx][None, :] + t[:, None]                    # seeds x point-candidates
        near = np.abs(pred - pz[None, :]) <= (tol_px * np.abs(m))[:, None]
        quick = np.array([len({obs[i][0] for i in pidx[h]}) for h in near])
        order = np.argsort(-quick)[:top_seeds]

        def score(mm, tt):
            tol = tol_px * abs(mm)
            got, res, hit = {}, {}, {}
            for i in found:
                q = mm * sheet[i] + tt
                qp = Point(q.real, q.imag)
                best = None
                for xy, is_area, poly, _, fname in cands[i]:
                    if poly is not None and poly.is_valid and poly.contains(qp):
                        d, near = 0.0, q
                    else:
                        k = int(np.argmin(np.hypot(xy[:, 0] - q.real, xy[:, 1] - q.imag)))
                        d, near = float(math.hypot(xy[k, 0] - q.real, xy[k, 1] - q.imag)), xy[k, 0] + 1j * xy[k, 1]
                    if best is None or d < best[0]:
                        best = (d, near, fname)
                if best and best[0] <= tol:
                    got[i] = best[1]; res[i] = best[0]; hit[i] = best[2]
            return got, res, hit

        best = None
        to_ll = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        centre = complex(W / 2, -H / 2)
        for k in order:
            mm, tt = m[k], t[k]
            for _ in range(iters):                                               # refine: nearest point, refit
                got, res, hit = score(mm, tt)
                if len(got) < 2:
                    break
                idx = list(got)
                src, dst = sheet[idx], np.array([got[i] for i in idx])
                Am = np.c_[src, np.ones(len(src))]
                sol = np.linalg.lstsq(Am, dst, rcond=None)[0]
                m2, t2 = sol[0], sol[1]
                if abs(np.degrees(np.angle(m2))) > max_rot_deg or not (scale_range[0] <= abs(m2) <= scale_range[1]):
                    break
                mm, tt = m2, t2
            got, res, hit = score(mm, tt)
            n = len(set(hit.values()))
            rms = float(np.sqrt(np.mean(np.square(list(res.values()))))) if res else 1e9
            key = (n, -rms)
            c = mm * centre + tt
            alts.append((n, *to_ll.transform(c.real, c.imag), abs(mm) * diag))
            if best is None or key > best["key"]:
                best = {"key": key, "m": mm, "t": tt, "n": n, "rms": rms, "names": sorted(set(hit.values()))}
        results.append({"ci": ci, "n_found": len({obs[i][0] for i in found}), "crs": crs, **(best or {})})

    fits = [r for r in results if "m" in r]
    if not fits:
        state.evidence.append(Evidence("names_agree", 0, "deterministic", "gazetteer", note=f"no fit in {len(results)} areas"))
        return []
    fits.sort(key=lambda r: r["key"], reverse=True)
    top = fits[0]
    mm, tt, crs = top["m"], top["t"], top["crs"]
    # chance: the most names any placement agrees on that puts the sheet somewhere else (its centre more than one
    # ground diagonal of the sheet away), in this area or another
    c = mm * complex(W / 2, -H / 2) + tt
    lon0, lat0 = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform(c.real, c.imag)
    far = abs(mm) * diag
    runner = max([n for n, lo, la, _ in alts
                  if math.hypot((lo - lon0) * 111320 * math.cos(math.radians(lat0)), (la - lat0) * 110574) > far] or [0])
    a, b = mm.real, mm.imag
    # x' + i y' = m (x - i y) + t  ->  x' = a x + b y + tx ;  y' = b x - a y + ty
    T6 = (float(a), float(b), float(tt.real), float(b), float(-a), float(tt.imag))
    corners = [(0, 0), (W, 0), (W, H), (0, H), (0, 0)]
    wkt = "POLYGON((" + ",".join(f"{T6[0]*x + T6[1]*y + T6[2]:.2f} {T6[3]*x + T6[4]*y + T6[5]:.2f}" for x, y in corners) + "))"
    scale = abs(mm)
    state.evidence.extend([
        Evidence("names_agree", top["n"], "deterministic", "gazetteer", note=f"of {top['n_found']} found in the area; {top['names'][:8]}"),
        Evidence("names_agree_elsewhere", runner, "deterministic", "gazetteer", note="the most names a placement elsewhere (more than a sheet diagonal away) agrees on"),
        Evidence("names_rms_px", round(top["rms"] / scale, 1), "deterministic", "gazetteer", note=f"{top['rms']:.0f} m at {scale:.2f} m/px"),
        Evidence("names_read", len(texts), "deterministic", "gazetteer")])
    rot = math.degrees(math.atan2(b, a))
    return [Hypothesis(state.sheet.digest, T6, wkt, crs, float(min(1.0, top["n"] / 8)), "name_fit", (top["ci"],),
                       note=f"{top['n']} names agree; rms {top['rms']:.0f} m; {scale:.2f} m/px; rotation {rot:.1f} deg")]


register(Primitive("name_search_area", "gazetteer", True, ("cue",), "candidate",
                   "candidate areas from the record's hint, else from where the sheet's different names cluster in the world gazetteer (OSM via Nominatim, per sheet)",
                   name_search_area, "generic", requires=("network: Nominatim",)))
register(Primitive("name_fit", "gazetteer", True, ("cue", "candidate"), "hypothesis",
                   "similarity that puts the most different sheet names on gazetteer features of the same name (OSM via Overpass, per sheet); nearest point of lines, inside of areas",
                   name_fit, "generic", requires=("network: Overpass",)))


# -- refine on the water ------------------------------------------------------------------------------------------
def _lonlat_fit(h, W: int, H: int):
    """The hypothesis as a sheet px -> lon/lat poly2 fit (what the water check takes)."""
    from pyproj import Transformer
    from .generic import fit_transform
    a, b, c, d, e, f = h.transform
    gx, gy = np.meshgrid(np.linspace(0, W, 8), np.linspace(0, H, 8))
    px = np.c_[gx.ravel(), gy.ravel()]
    X, Y = a * px[:, 0] + b * px[:, 1] + c, d * px[:, 0] + e * px[:, 1] + f
    lon, lat = Transformer.from_crs(h.crs, "EPSG:4326", always_xy=True).transform(X, Y)
    ll = np.c_[lon, lat]
    coeffs, _ = fit_transform(px, ll, "poly2")
    return coeffs, (float(ll[:, 0].min()), float(ll[:, 1].min()), float(ll[:, 0].max()), float(ll[:, 1].max()))


def water_refine(state, rounds: int = 6, pad_min: float = 1.2, res_m: float = 20.0, min_response: float = 0.05,
                 settle_m: float = 30.0, agree_m: float = 60.0, max_step_scale: float = 0.08, max_step_rot_deg: float = 4.0,
                 coarse_m: float = 100.0, quad_tol_m: float = 150.0, max_move_rms: float = 4.0):
    """Move a names placement onto the water: the sheet's blue plate against OpenStreetMap's water (the comparison
    basemap_agreement makes), over the footprint widened by pad_min arc-minutes (~2 km, more than a names placement
    is off). Each round measures the shift of the whole sheet and of each quadrant; with three or four quadrants
    that correlate, the quadrant shifts fit a similarity correction (shift, scale, rotation: the names fit gets
    scale and rotation from labels that sit beside their features), else the whole-sheet shift is applied. Stops
    when the shifts settle. Puts the moved placement first (inserted directly; the primitive returns evidence) and
    leaves water_locked (last whole-sheet shift under agree_m with a clear response), water_local_agree (every
    comparable quadrant under agree_m, at least three) and water_moved_m (how far the sheet centre moved)."""
    from .basemap import basemap_shift, rgb_of, _local_evidence
    if not state.hypotheses or state.hypotheses[0].matcher != "name_fit":
        return []
    h0 = state.hypotheses[0]
    W, H = state.sheet.meta.get("width", 0), state.sheet.meta.get("height", 0)
    rgb = rgb_of(state.sheet.image)
    M = complex(h0.transform[0], h0.transform[1])            # px -> metres: M (x - i y) + tau
    tau = complex(h0.transform[2], h0.transform[5])
    quarters = np.array([complex(W / 4, -H / 4), complex(3 * W / 4, -H / 4), complex(W / 4, -3 * H / 4), complex(3 * W / 4, -3 * H / 4)])
    centre = complex(W / 2, -H / 2)
    c0 = M * centre + tau
    r, how = None, []
    for _ in range(rounds):
        T6 = (M.real, M.imag, tau.real, M.imag, -M.real, tau.imag)
        coeffs, bounds = _lonlat_fit(Hypothesis(h0.sheet, T6, h0.site_wkt, h0.crs, h0.score, h0.matcher), W, H)
        try:
            r_new = basemap_shift(rgb, coeffs, "poly2", "EPSG:4326", bounds, pad_min, res_m=res_m, margin=1.0)
        except RuntimeError as e:
            r_new = {"why": str(e)[:160]}
        bad = r_new.get("why") or (r_new["response"] < min_response and f"no clear correlation (response {r_new['response']:.3f})")
        if bad:
            if r is None:
                return [Evidence("water_locked", None, "deterministic", "basemap", note=bad)]
            M, tau = prev                               # the last step lost the water: undo it and stop
            how.append("x")
            break
        r, prev = r_new, (M, tau)
        glob = complex(r["dx_m"], r["dy_m"])
        # coarse first: the whole sheet until it is close; then the quadrants that agree with the whole (a quadrant
        # far from it has locked onto another river) fit scale and rotation
        q = [(k, complex(x["dx_m"], x["dy_m"])) for k, x in enumerate(r.get("local") or [])
             if x and x["response"] >= min_response and abs(complex(x["dx_m"], x["dy_m"]) - glob) <= quad_tol_m]
        if abs(glob) <= coarse_m and len(q) >= 3:
            src = M * quarters[[k for k, _ in q]] + tau
            dst = src + np.array([v for _, v in q])
            A = np.c_[src, np.ones(len(src))]
            mc, tc = np.linalg.lstsq(A, dst, rcond=None)[0]
            if abs(abs(mc) - 1) <= max_step_scale and abs(math.degrees(np.angle(mc))) <= max_step_rot_deg:
                if abs(glob) <= settle_m and max(abs(v) for _, v in q) <= settle_m:
                    break
                M, tau = mc * M, mc * tau + tc
                how.append("q"); continue
        if abs(glob) <= settle_m:
            break
        tau = tau + glob
        how.append("g")
    last = math.hypot(r["dx_m"], r["dy_m"])
    moved = (M * centre + tau) - c0
    # the water may only move the sheet as far as the names leave it uncertain: a lock farther away is another river
    rms_px = next((e.value for e in reversed(state.evidence) if e.name == "names_rms_px"), None)
    reach = max_move_rms * float(rms_px) * abs(complex(h0.transform[0], h0.transform[1])) if rms_px else float("inf")
    locked = bool(last <= agree_m and abs(moved) <= reach)
    T6 = (float(M.real), float(M.imag), float(tau.real), float(M.imag), float(-M.real), float(tau.imag))
    corners = [(0, 0), (W, 0), (W, H), (0, H), (0, 0)]
    wkt = "POLYGON((" + ",".join(f"{T6[0]*x + T6[1]*y + T6[2]:.2f} {T6[3]*x + T6[4]*y + T6[5]:.2f}" for x, y in corners) + "))"
    if locked and how.count("x") < len(how):
        state.hypotheses.insert(0, Hypothesis(h0.sheet, T6, wkt, h0.crs, h0.score, "name_fit+water", h0.candidates,
                                              note=f"{h0.note}; moved {abs(moved):.0f} m onto the water ({''.join(how)})"))
    loc = _local_evidence(r, agree_m, min_response, min_quadrants=3)
    return [Evidence("water_locked", locked, "deterministic", "basemap",
                     note=f"moved {abs(moved):.0f} m (east {moved.real:+.0f}, north {moved.imag:+.0f}) in steps {''.join(how) or '-'}; "
                          f"{'' if abs(moved) <= reach else f'farther than the names allow ({reach:.0f} m); '}scale x{abs(M) / abs(complex(h0.transform[0], h0.transform[1])):.3f}; last shift {last:.0f} m, response {r['response']:.3f}, sheet water {r['water']:.1%}"),
            Evidence("water_moved_m", round(float(abs(moved)), 1), "deterministic", "basemap"),
            Evidence("water_local_agree", loc.value, "deterministic", "basemap", note=loc.note)]


register(Primitive("water_refine", "basemap", True, ("hypothesis",), "evidence",
                   "a names placement moved onto OpenStreetMap's water by phase correlation of the sheet's blue plate (pinned vector tiles), until the shift settles",
                   water_refine, "generic", requires=("opencv", "network: OSM vector tiles")))
