---
id: street-names-as-geometry
kinds: [street_map, planning_drawing, historical_map]
cues: [road, place]
method: street names as geometry: junction votes locate, label-to-centreline fit places
---
A sheet with many street names can be placed without any image matching. Two steps. Locate: look every name up in
the road network of the area (a GeoPackage of named road centrelines, or OSM); every pair of names whose roads meet
within ~150 m votes for that junction; the densest cluster of votes is where the sheet is. Fit: assign each road
label on the sheet to its road by fuzzy name match, then find the similarity (scale, rotation, translation) that
puts every label pixel onto its own road's centreline: sweep rotation (5°) and scale (log-spaced from 0.02 to 40
m/px), and for each pair sweep translation on a grid, scoring poses by labels within ~60 m of their road using
distance-transformed road rasters (vectorised); refine the best by point-to-line ICP on its inliers. Label angles
are not needed. Verify with a family the fit did not use: place names (not roads) found inside the footprint. Old
maps lose the streets that were renamed or removed, so expect half the labels to fit and a wider tolerance.
