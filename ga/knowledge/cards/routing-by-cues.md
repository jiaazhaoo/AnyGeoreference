---
id: routing-by-cues
kinds: [any]
cues: [road, number, place, landmark, arrow, scale, grid, text]
method: the first question is what on this sheet ties it to the Earth; the answer picks the recipe
tags: [decision table, route, workflow, which method, start here]
see: [routing-coarse-to-fine, reading-the-sheet, build-capability-determination]
---
Every georeferencing job starts with one question: what on this sheet ties it to the Earth? The reading answers
it, and the answer picks the method. Printed coordinates or a graticule -> control points for free, fit a polynomial
(family-survey-graticule). Grid figures on the margins or a sheet number of a known series -> the sheet index or the
grid labels give the bounds before any matching (family-grid-and-series-sheets). Many street names -> street names as
geometry: junction votes locate, label-to-centreline fit places (matcher-street-names-geometry). Road names plus house
numbers -> text anchors against an address register (matcher-text-anchors). Place names only, no roads -> toponym
constellation fit against a gazetteer (matcher-toponym-constellation). Coastline, rivers, rail but no readable text
-> polyline shape matching or a learned image matcher over a hinted area (matcher-polyline-shape, matcher-learned-image).
Building outlines or parcel boundaries at large scale -> footprint or parcel matching (matcher-building-footprints,
matcher-parcel-boundaries). Another edition of the same series already georeferenced -> map-to-map matching, the
easiest case of all (matcher-map-to-map-editions). A photograph -> decide first whether it is vertical (projective
fit possible) or oblique (locate the viewpoint, do not georeference). Nothing of the above (a floor plan, a section,
a diagram) -> abstain with the reason. Several routes can apply to one sheet; run the cheapest that gives a candidate
area first, then the one that gives a fit, then a verification from a family the fit did not use. The route is a
plan, written down, with the truth source and the stop rule beside it; it is not improvised step by step.
