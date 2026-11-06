---
id: matcher-building-footprints
kinds: [planning_drawing, street_map]
cues: [landmark]
method: building outlines on a large-scale sheet matched to a footprint layer by shape and arrangement
tags: [building footprints, outlines, blocks, shape context, polygon matching, IoU, large scale, OS buildings, OSM buildings]
see: [family-town-plans, family-planning-drawings, matcher-parcel-boundaries, verify-overlay-dense-networks]
buildable: yes
effort: one day: outline extraction (closed dark polygons or filled blocks), footprint layer for the area, arrangement matching by pairwise centroid geometry, then polygon-level ICP and IoU score
ingredients: a building footprint layer for the candidate area; the sheet's building mask (by colour or fill); shapely, numpy, OpenCV
---
At 1:500 to 1:2,500 every building is drawn, and buildings are distinctive: a terrace of eight, an L-shaped
church, a detached house with an outbuilding. Extract building polygons from the sheet (filled or hatched blocks,
or closed outlines), extract footprints from the reference layer over the candidate area, and match the
arrangement: centroids as a point pattern (the constellation method) for the coarse pose, then polygon-to-polygon
alignment (ICP on outline points) for the fine pose, scored by the mean intersection over union of matched
buildings. Buildings change more than roads (demolished, extended, rebuilt), so the score is the share of sheet
buildings with a footprint match above an IoU of about 0.5, and a third of them matching is normal on a sheet
fifty years old. Use building matching as the fine step after a street-name or address placement, or as the
verification family for a placement made from names: the names did not use the buildings. A drawing traced from an
old base map shows buildings that the modern layer lacks and lacks the new ones; neither is evidence against a
placement, only a building where the reference has a different building is.
