---
id: reference-road-networks
kinds: [street_map, planning_drawing, historical_map]
cues: [road]
method: named road centrelines are the geometry that street names turn into; names need normalising and an epoch
tags: [road network, centrelines, OS Open Roads, Zoomstack, OSM highway, named roads, name normalisation, renamed streets, roads_near]
see: [matcher-street-names-geometry, reference-historic-epoch, reading-text-spotting]
primitives: [road_junction_locate, road_name_fit]
---
A named road-centreline layer (a national open roads set with names, or OSM highways with the name tag) turns every
street name into a polyline, and a street-name matcher is then pure geometry. Normalise names on both sides: case,
Street/St, Road/Rd, Avenue/Ave, Lane/Ln, Great/Gt, Upper/Lower, Saint/St, apostrophes and hyphens, numerals
(Fourth/4th); match fuzzily (token ratio above ~85) and keep the top two candidates per label. Roads of the same name
in different towns are the reason to locate by junction votes before fitting: two names whose roads meet exist in
one place only. Old maps name streets that are gone: cleared, renamed after a war, merged into a ring road; main
roads, roads along rivers and rail, and streets named after the parish church survive best. For sheets before about
1950 add a historical road source where one exists (a georeferenced old edition, a historical gazetteer's road
entries) and expect half the labels not to match on a modern network. A road name match is a cue, not a position:
the position is the centreline, and a label is accepted where its pixel lands within a tolerance (about 60 m at town
scale) of its own road, never of any road.
