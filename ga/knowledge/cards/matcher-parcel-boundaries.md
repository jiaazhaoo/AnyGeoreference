---
id: matcher-parcel-boundaries
kinds: [historical_map]
cues: [number, text]
method: cadastral parcel outlines matched to a modern parcel or field-boundary layer by shape, verified by acreage
tags: [parcel, cadastral, field boundaries, hedges, polygon matching, acreage check, apportionment, tithe, enclosure]
see: [family-cadastral-estate, matcher-polyline-shape, matcher-building-footprints, verify-catalogue]
buildable: yes
effort: one day: parcel extraction (closed regions of the boundary mask), boundary-layer polylines for the parish, chamfer-and-ICP pose, acreage verification against the apportionment
ingredients: a parcel or topographic boundary layer (field boundaries, hedges) for the parish; the apportionment table where it exists (parcel number to acreage); the sheet's boundary mask; shapely, numpy, OpenCV
---
Field boundaries in long-enclosed countryside persist for centuries, so the network of parcel edges on a tithe,
enclosure or estate map matches the modern boundary layer as a line network even where every name has changed.
Treat the parcel edges as polylines and match them by chamfer and ICP over a rotation-and-scale sweep (the scale is
in chains, often unstated; the sweep finds it); the parish polygon from the gazetteer is the candidate area. The
verification family is unique to this kind: the apportionment lists every parcel's acreage, and under the fitted
transform each extracted parcel's area must agree within a few percent (1 acre is 4,047 square metres); a fit with
the right shape and the wrong scale fails the acreages. Parcels merged since (hedges removed in the 20th century)
make large modern fields that contain several old parcels: match old edges to the modern edges that remain and
ignore the removed ones, and do not expect a modern edge for every old one. Deliver the parcels as polygons with
their numbers, which makes the apportionment a spatial table.
