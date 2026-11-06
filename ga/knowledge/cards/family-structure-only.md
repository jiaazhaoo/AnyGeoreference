---
id: family-structure-only
kinds: [raster_no_text]
cues: []
method: edges or linework against rendered reference vectors over a hinted area
tags: [no text, structure, linework, edges, roads rail water, hint, render, overlay]
see: [matcher-render-and-correlate, matcher-learned-image, matcher-polyline-shape, verify-overlay-dense-networks]
primitives: [edge_structure, hint_area, reference_render, structure_match_orb, overlay_agreement]
---
With no readable text the only cue is structure: roads, rail, water, parcel outlines, building blocks. A candidate
area must come from the record, a user hint, the sheet series or a coarse geocode; without one, abstain with
"no candidate area". Render reference line layers over the area on a metric grid in the sheet's own style (line
widths in pixels matched to the scan's, black on white), extract edges or skeletonised linework from the image,
match (ORB plus RANSAC as the floor, a learned cross-modal matcher as the method, chamfer matching of polylines as
the alternative), and verify by overlay: the share of image structure within a few pixels of reference structure,
compared with the same share under a 200 m shifted hypothesis so that dense networks do not pass by chance. A
rotated, shifted road render with a hint 0.5 km off came back to 5-7 m at the corners; hand-drawn plans did not
match with the generic matcher at all, the learned matcher placed half of them. Paint out printed graticules and
grid lines before structure matching: the reference has none and the matcher will lock onto them.
