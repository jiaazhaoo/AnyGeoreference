---
id: family-town-plans
kinds: [street_map, historical_map]
cues: [road, place, landmark, scale, arrow]
method: large-scale town plans place by street names as geometry, then buildings or landmarks for the fine fit
tags: [town plan, city plan, 1:500, 1:1056, 1:2500, street names, blocks, landmarks, churches, insurance plans, Goad]
see: [matcher-street-names-geometry, matcher-building-footprints, reference-road-networks, reference-historic-epoch]
primitives: [road_junction_locate, road_name_fit, places_in_footprint]
---
Town plans between 1:500 and 1:10,000 (OS town plans at 1:500 and 1:1,056, Goad fire-insurance plans, 19th-century
commercial city maps, modern street maps and the OSM renders people paste into reports) carry dozens of street names
and the outlines of blocks. Street names are the method: look every readable name up in the road network of the
region, every pair of names whose roads meet within ~150 m votes for a junction, the densest cluster of votes is the
town and the square kilometre; then fit a similarity that puts each label on its own centreline. Expect half the
labels of a map older than 1900 not to fit: streets renamed, slums cleared, ring roads cut through; use the
persistent ones (main roads, railways, rivers, churches, market places). A pre-1900 plan often has no north arrow and
north is not up; the fit sweeps rotation, so that is not a problem, but the scale needs a bound (2 cm to 5 m per
pixel for this family) to keep the sweep honest. Verify with place names and landmarks found inside the footprint
that the fit did not use, or with building-block outlines against the modern footprint layer where the old town
survives. Insurance plans and OS 1:500 plans also carry house numbers: they turn the problem into text anchors.
