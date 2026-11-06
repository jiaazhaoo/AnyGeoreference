---
id: structure-only-rasters
kinds: [raster_no_text]
cues: []
method: edges or linework against rendered reference vectors over a hinted area
---
With no readable text the only cue is structure: roads, rail, water, parcel outlines. A candidate area must come from
the record, a user hint or a coarse geocode; without one, abstain. Render reference line layers over the area on a
metric grid, extract edges or skeletonised linework from the image, match (ORB + RANSAC as the floor, a learned
matcher as the method), and verify by overlay: the share of image structure within a few pixels of reference structure.
A rotated, shifted road render with a hint 0.5 km off came back to 5-7 m at the corners; hand-drawn plans did not match
with the generic matcher at all.
