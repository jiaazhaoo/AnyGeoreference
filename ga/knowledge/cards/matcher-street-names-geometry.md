---
id: matcher-street-names-geometry
kinds: [street_map, planning_drawing, historical_map]
cues: [road, place]
method: street names as geometry: junction votes locate, label-to-centreline fit places
tags: [street names, junction votes, label to centreline, distance transform, rotation scale sweep, ICP, named roads, no image matching]
see: [family-town-plans, reference-road-networks, verify-places-in-footprint, routing-coarse-to-fine]
primitives: [road_junction_locate, road_name_fit, places_in_footprint]
buildable: yes
effort: one day: a locate function (junction votes), a fit function (vectorised sweep + ICP), a verification (places inside)
ingredients: named road centrelines for the region (open roads layer or OSM); the reader's street-name cues with boxes; numpy, OpenCV distance transform, shapely
---
A sheet with many street names can be placed without any image matching. Two steps. Locate: look every name up in
the road network of the region (a GeoPackage of named road centrelines, or OSM); every pair of names whose roads meet
within ~150 m votes for that junction; the densest cluster of votes is where the sheet is. Fit: assign each road
label on the sheet to its road by fuzzy name match, then find the similarity (scale, rotation, translation) that
puts every label pixel onto its own road's centreline: sweep rotation (5 degrees) and scale (log-spaced from 0.02 to
40 m/px), and for each pair sweep translation on a grid, scoring poses by labels within ~60 m of their road using
distance-transformed road rasters (one raster per road, vectorised); refine the best by point-to-line ICP on its
inliers. Label angles are not needed. Verify with a family the fit did not use: place names (not roads) found inside
the footprint, or building blocks against footprints. Old maps lose the streets that were renamed or removed, so
expect half the labels to fit and a wider tolerance. Measured: an 1823 town plan placed at 125 m and a modern
suburb render at 371 m from the archive's own placement, both accepted on the second family; both had been
abstentions while this matcher was missing from the library, which is the lesson: the planner is only as good as
the library, add the tool.
