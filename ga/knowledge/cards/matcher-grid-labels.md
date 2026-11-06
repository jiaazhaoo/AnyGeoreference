---
id: matcher-grid-labels
kinds: [historical_map, planning_drawing]
cues: [grid]
method: grid figures printed on the margins or on the face give control points in the projected CRS directly
tags: [grid figures, eastings, northings, kilometre squares, UTM, MGRS, National Grid, grid lines, projected CRS]
see: [family-grid-and-series-sheets, matcher-graticule-corners, geodesy-crs-and-outputs]
primitives: [grid_figures, control_point_fit]
buildable: yes
effort: in the library for figures on the face; margin figures with zone letters are hours
ingredients: the reader's grid cues (text and box); the grid's CRS from the series; numpy
---
Modern and mid-century sheets print the grid: kilometre lines across the face with their eastings and northings in
the margins (often the last two or three digits only, the full value at the corners), or the 100 km square letters
and a UTM zone in the notes. Each grid line read with its value is a line constraint; two crossing lines are a
control point in the projected CRS, no projection or datum step needed, and the fit is a similarity or affine in
metres with a residual that should be under a pixel or two. Abbreviated figures are completed from the corner
values or from the candidate area (a "36" easting near a known town is 436 km, not 536). Grid lines are also the
rotation exactly and the scale exactly (1 km between lines over N pixels). On planning drawings the grid appears as
crosses or as a frame with figures and is the best cue when present. Beware the grid of a different system on
reprinted sheets (a military grid over a civil sheet) and figures in a unit other than metres (yards on some
mid-century grids): the series tells.
