"""verify-neighbour-sheets: two sheets declared halves of the same plan must tile along their shared edge. Each
sheet already carries its own fitted transform (sheet px -> the common CRS); this primitive samples the road cues
within a margin of the abutting edge on the current sheet, reads the same for the neighbour sheet from the
sheet's own meta (no second State exists inside one loop run), matches roads across the seam by name, extrapolates
each road's near-edge samples to the exact point where its centreline crosses the seam, transforms that crossing
point through each sheet's own fit into the CRS, and measures the offset between the two sheets' crossing points
for the same road, split into a component perpendicular to the seam (gap / overlap) and a component along the
seam (continuity / jump). Reader-independent and geometry-only: no model, no network. See verify-neighbour-sheets
in the knowledge base.

Sheet.meta carries the neighbour's data at batch-assembly time (the orchestrator knows the index positions and
which edges adjoin), under "neighbours" (a list) or "neighbour" (one dict), each:
  side:      which edge of *this* sheet touches the neighbour: "left" | "right" | "top" | "bottom"
  width,
  height:    the neighbour's pixel size
  transform: the neighbour's own accepted 6-coefficient affine, sheet px -> CRS (the same CRS as this sheet's)
  roads:     [{"name": str, "points": [[x, y], ...]}, ...] sample points along each named road's centreline, in
             the neighbour's own sheet-pixel space (as this sheet's own road samples are state.cues of kind "road")
"""
from __future__ import annotations

import difflib

import numpy as np

from .. import Primitive, register
from evalcore import Evidence

SIDES = ("left", "right", "top", "bottom")
OPPOSITE = {"left": "right", "right": "left", "top": "bottom", "bottom": "top"}

_WORD = {
    "street": "st", "road": "rd", "avenue": "ave", "lane": "ln", "great": "gt", "saint": "st",
    "first": "1st", "second": "2nd", "third": "3rd", "fourth": "4th", "fifth": "5th", "sixth": "6th",
}


def _norm_name(name: str) -> str:
    s = name.strip().lower().replace("'", " ").replace("-", " ")
    return " ".join(_WORD.get(t, t) for t in s.split())


def _name_pairs(cur_names, nbr_names, thresh: float):
    """Greedy best match: each current-sheet name claims its best unclaimed neighbour name, above `thresh`."""
    used, pairs = set(), []
    for cn in cur_names:
        ncn = _norm_name(cn)
        best, best_score = None, 0.0
        for nn in nbr_names:
            if nn in used:
                continue
            score = 1.0 if ncn == _norm_name(nn) else difflib.SequenceMatcher(None, ncn, _norm_name(nn)).ratio()
            if score > best_score:
                best, best_score = nn, score
        if best is not None and best_score >= thresh:
            pairs.append((cn, best))
            used.add(best)
    return pairs


def _apply(transform, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = transform
    return a * x + b * y + c, d * x + e * y + f


def _edge_dist(x: float, y: float, side: str, width: float, height: float) -> float:
    return {"right": width - x, "left": x, "top": y, "bottom": height - y}[side]


def _margin_lists(points_fn, source, width, height, side, margin_px):
    groups: dict[str, list] = {}
    for name, x, y in points_fn(source):
        d = _edge_dist(x, y, side, width, height)
        if 0.0 <= d <= margin_px:
            groups.setdefault(name, []).append((x, y))
    return groups


def _cue_points(cues):
    for c in cues:
        if c.kind == "road" and c.text.strip():
            x0, y0, x1, y1 = c.bbox
            yield c.text.strip(), (x0 + x1) / 2.0, (y0 + y1) / 2.0


def _road_list_points(roads):
    for r in roads or []:
        name = (r.get("name") or "").strip()
        if name:
            for x, y in r.get("points", []):
                yield name, float(x), float(y)


def _cross_point(points, side: str, width: float, height: float) -> tuple[float, float]:
    """Extrapolate near-edge samples of one road to where its centreline crosses the edge exactly (least squares
    line through the samples; a single sample falls back to its own position on the seam)."""
    pts = np.asarray(points, float)
    vertical = side in ("left", "right")
    seam = (0.0 if side in ("left", "top") else (width if vertical else height))
    u, v = (pts[:, 0], pts[:, 1]) if vertical else (pts[:, 1], pts[:, 0])
    if len(pts) >= 2 and float(np.ptp(u)) > 1e-6:
        m, c = np.linalg.lstsq(np.c_[u, np.ones_like(u)], v, rcond=None)[0]
        v0 = m * seam + c
    else:
        v0 = float(v.mean())
    return (seam, v0) if vertical else (v0, seam)


def neighbour_sheet_tiling(state, margin_px: float = 100.0, tol_m: float = 60.0, min_roads: int = 2, name_sim: float = 0.85):
    if not state.hypotheses:
        return []
    width, height = state.sheet.meta.get("width"), state.sheet.meta.get("height")
    if not width or not height:
        return []
    neighbours = state.sheet.meta.get("neighbours")
    if neighbours is None:
        one = state.sheet.meta.get("neighbour")
        neighbours = [one] if one else []
    if not neighbours:
        return []

    h = state.hypotheses[0]
    out = []
    for nb in neighbours:
        nb = nb or {}
        side = nb.get("side")
        nwidth, nheight, nb_transform, nb_roads = nb.get("width"), nb.get("height"), nb.get("transform"), nb.get("roads")
        if side not in SIDES or not (nwidth and nheight and nb_transform and nb_roads):
            continue

        cur_groups = _margin_lists(_cue_points, state.cues, width, height, side, margin_px)
        nbr_groups = _margin_lists(_road_list_points, nb_roads, nwidth, nheight, OPPOSITE[side], margin_px)
        if not cur_groups or not nbr_groups:
            out.append(Evidence("neighbour_tiling_roads_matched", 0, "deterministic", "road-network",
                                 note=f"side={side}; no road pixels within {margin_px} px of the seam on one or both sheets"))
            continue

        pairs = _name_pairs(list(cur_groups), list(nbr_groups), name_sim)
        if not pairs:
            out.append(Evidence("neighbour_tiling_roads_matched", 0, "deterministic", "road-network",
                                 note=f"side={side}; {len(cur_groups)} vs {len(nbr_groups)} named roads near the seam, none matched"))
            continue

        # the perpendicular / along-edge basis, from this sheet's own edge line (both sides should agree on it)
        if side in ("left", "right"):
            ex = 0.0 if side == "left" else float(width)
            p1, p2 = _apply(h.transform, ex, 0.0), _apply(h.transform, ex, float(height))
        else:
            ey = 0.0 if side == "top" else float(height)
            p1, p2 = _apply(h.transform, 0.0, ey), _apply(h.transform, float(width), ey)
        evec = np.array(p2) - np.array(p1)
        elen = float(np.linalg.norm(evec))
        if elen < 1e-9:
            continue
        edir = evec / elen
        enorm = np.array([-edir[1], edir[0]])

        offsets, perp, along, used_names = [], [], [], []
        for cn, nn in pairs:
            cur_px = _cross_point(cur_groups[cn], side, width, height)
            nbr_px = _cross_point(nbr_groups[nn], OPPOSITE[side], nwidth, nheight)
            cur_pt, nbr_pt = np.array(_apply(h.transform, *cur_px)), np.array(_apply(nb_transform, *nbr_px))
            d = nbr_pt - cur_pt
            offsets.append(float(np.linalg.norm(d)))
            perp.append(float(np.dot(d, enorm)))
            along.append(float(np.dot(d, edir)))
            used_names.append(cn if cn == nn else f"{cn}~{nn}")

        offsets_a = np.asarray(offsets)
        mean_offset, spread = float(offsets_a.mean()), float(offsets_a.std())
        n_continuing = int(np.sum(offsets_a <= tol_m))
        accepted = bool(mean_offset <= tol_m and n_continuing >= min_roads)
        note = (f"side={side}; matched {', '.join(used_names)}; offsets_m={[round(o, 1) for o in offsets]}; "
                f"perp_m={[round(p, 1) for p in perp]}; along_m={[round(a, 1) for a in along]}; "
                f"tol {tol_m} m; {n_continuing}/{len(pairs)} continue without a jump (need >= {min_roads})")
        out.append(Evidence("neighbour_tiling_mean_offset_m", round(mean_offset, 2), "deterministic", "road-network", note=note))
        out.append(Evidence("neighbour_tiling_offset_spread_m", round(spread, 2), "deterministic", "road-network", note=note))
        out.append(Evidence("neighbour_tiling_roads_matched", len(pairs), "deterministic", "road-network", note=note))
        out.append(Evidence("neighbour_tiling_accepted", accepted, "deterministic", "road-network", note=note))
    return out


register(Primitive(
    "neighbour_sheet_tiling", "road-network", True, ("hypothesis",), "evidence",
    "road centrelines sampled within ~100 px of the shared edge on each of two abutting sheets (the current "
    "sheet's own road cues; the neighbour's equivalent carried in the sheet's meta), matched by name, "
    "extrapolated to the seam and transformed through each sheet's own fitted transform into the common CRS; "
    "the mean perpendicular + along-edge offset of matched roads is the tiling evidence, accepted near a ~60 m "
    "tolerance with at least two named roads continuing across the seam without a jump",
    neighbour_sheet_tiling, "generated"))
