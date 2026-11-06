---
id: family-cadastral-estate
kinds: [historical_map]
cues: [number, place, text, scale]
method: cadastral, tithe, enclosure and estate maps place by parcel boundaries that persist and by the apportionment
tags: [cadastral, tithe map, enclosure, estate map, parcel, field names, apportionment, chains, surveyor, pre-OS]
see: [matcher-parcel-boundaries, geodesy-prime-meridians-and-units, reference-historic-epoch, matcher-polyline-shape]
---
Tithe maps (England and Wales, 1836-1850s), enclosure awards, estate surveys and continental cadastres show parcels
with numbers keyed to a written apportionment (owner, occupier, field name, acreage), roads, streams, buildings and
sometimes field names on the map itself. No grid, no graticule, often no north, scales in chains to the inch (3, 4
or 6 chains to the inch, i.e. 1:2,376, 1:3,168, 1:4,752). What persists: hedged field boundaries in rural Britain
(many survive into the modern topographic parcel layer), roads, streams, parish boundaries, churches, mills, the
village street pattern. What does not: field numbers (meaningless outside the apportionment), owners, most buildings.
Method: find the parish from the title and the apportionment (gazetteer), take the parish polygon as the candidate
area, extract parcel outlines from the map as polylines, match them to the modern boundary layer by shape (chamfer
or ICP after a rotation-and-scale sweep), and verify by the acreages: a parcel's area under the fitted transform must
match its apportionment acreage within a few percent, a family independent of the shape match. A road name or a
field name confirmed in a historical gazetteer (the OS six-inch transcriptions of 1888-1913) is a second family.
Expect 5-20 m accuracy; a surveyor's chain map was never better than that.
