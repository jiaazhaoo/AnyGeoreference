"""System-wide rules every placement obeys, whichever matcher made it (bound, generic, or written by the builder).
They enforce in code what the knowledge base states in prose:

- failure-rotation-and-mirror: a placement that mirrors the sheet is refused unless the sheet was found mirrored
  (Evidence `sheet_mirrored` True, e.g. a negative or a text test);
- transforms-choice-and-gcps: a placement whose scale is outside any map's range, or whose two axes differ in scale by
  more than paper and scanners ever do, is a degenerate fit, refused;
- verify-evidence-families: a check counts as a second family only when the reference it consulted is not one the
  matcher itself consumed (`independent_facts`).

A refused placement is recorded as Evidence `hypothesis_rejected` with its reason, so the trace shows it."""
from __future__ import annotations

import math

MAX_AXIS_RATIO = 1.6          # paper shrinks ~2 %, scanners stretch a few %; 60 % is a broken fit, not a map
MPP_RANGE = (0.001, 20000.0)  # 1 mm/px (a drawing scanned at 1200 dpi) to 20 km/px (a world map thumbnail)

# the reference families each matcher's fit consumed (the reader is shared by every route and not counted)
REFERENCES_USED = {
    "text_anchor_fit": ("address-register", "gazetteer"),
    "road_name_fit": ("road-network",),
    "control_point_fit": ("printed-grid",),
    "grid_figures": ("printed-grid",),
    "plan_minima_match": ("basemap",),
    "structure_match": ("basemap",),
    "structure_match_orb": ("basemap",),
    "toponym_constellation_fit": ("gazetteer",),
}
# the facts the policies treat as a second family, by evidence name
SECOND_FAMILY_FACTS = ("places_in_footprint", "address_in_footprint", "overlay_agreement", "editions_agree", "batch_agreement", "matchers_agree",
                       "basemap_agree", "partner_basemap_agree")


def references_of(matcher: str) -> set[str]:
    """Reference families behind a matcher (a composite name 'a+b' unions its parts). Unknown matchers fall back to
    the family the library declares for them, unless that family is generic geometry or the reader."""
    from .primitives import LIBRARY
    out: set[str] = set()
    for part in str(matcher).split("+"):
        if part in REFERENCES_USED:
            out |= set(REFERENCES_USED[part])
        elif part in LIBRARY:
            p = LIBRARY[part]
            out |= set(getattr(p, "uses", ()) or (() if p.family in ("geometry", "sheet-reader") else (p.family,)))
    return out


def _geographic(crs) -> bool:
    """Degrees, whatever the datum (any geographic CRS pyproj knows)."""
    try:
        from pyproj import CRS
        return CRS.from_user_input(crs).is_geographic
    except Exception:                                           # noqa: BLE001
        return str(crs).upper() in ("EPSG:4326", "WGS84")


def _linear_in_metres(h) -> tuple[float, float, float, float, float]:
    import shapely.wkt
    a, b, c, d, e, f = h.transform
    kx = ky = 1.0
    if _geographic(h.crs):
        try:
            lat0 = shapely.wkt.loads(h.site_wkt).centroid.y
        except Exception:                                       # noqa: BLE001
            lat0 = f
        kx, ky = 111320.0 * math.cos(math.radians(lat0)), 110574.0
    return a * kx, b * kx, d * ky, e * ky, a * e - b * d


def check(h, state) -> str | None:
    """None if the placement is admissible, else the reason it is refused."""
    A, B, D, E, det = _linear_in_metres(h)
    if not all(map(math.isfinite, (A, B, D, E))):
        return "non-finite transform"
    mirrored_ok = any(getattr(ev, "name", "") == "sheet_mirrored" and ev.value is True for ev in state.evidence)
    if det > 0 and not mirrored_ok:                   # sheet y runs down, CRS y runs north: a proper placement has det < 0
        return "mirrors the sheet (no evidence the sheet is mirrored)"
    s = sorted([math.hypot(A, D), math.hypot(B, E)])
    if s[0] <= 0:
        return "degenerate: zero scale on one axis"
    if s[1] / s[0] > MAX_AXIS_RATIO:
        return f"degenerate: axis scales differ {s[1] / s[0]:.2f}x"
    mpp = math.sqrt(s[0] * s[1])
    if not MPP_RANGE[0] <= mpp <= MPP_RANGE[1]:
        return f"degenerate: {mpp:.4g} m/px outside any map's range"
    return None


def independent_facts(facts: dict, state) -> tuple[dict, list[str]]:
    """Mask second-family facts that consulted a reference the best placement's matcher already consumed."""
    if not state.hypotheses:
        return facts, []
    best = state.hypotheses[0]
    used = references_of(best.matcher)
    masked = []
    out = dict(facts)
    for ev in state.evidence:
        if ev.name in SECOND_FAMILY_FACTS and ev.name != "matchers_agree" and ev.family in used and out.get(ev.name) is not None:
            out[ev.name] = None; masked.append(f"{ev.name} ({ev.family} also used by {best.matcher})")
    other = next((h for h in state.hypotheses[1:] if h.matcher != best.matcher), None)
    if out.get("matchers_agree") is not None and other is not None and (references_of(other.matcher) & used):
        out["matchers_agree"] = None; masked.append(f"matchers_agree ({best.matcher} and {other.matcher} share {sorted(references_of(other.matcher) & used)})")
    return out, masked
