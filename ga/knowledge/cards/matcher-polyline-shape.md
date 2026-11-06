---
id: matcher-polyline-shape
kinds: [historical_map, raster_no_text]
cues: [landmark]
method: coastline, river, rail or road shape matched as polylines by chamfer distance over a rotation-and-scale sweep, refined by ICP
tags: [polyline, coastline, river, railway, chamfer matching, ICP, distance transform, shape matching, curve matching, skeleton]
see: [family-nautical-charts, family-small-scale-thematic, family-cadastral-estate, matcher-render-and-correlate]
buildable: yes
effort: one day: linework extraction (colour or edge plus skeleton), reference polylines from a vector layer, chamfer score on a distance transform over the sweep, ICP refinement, chance-level check by shifted poses
ingredients: a vector layer of the class (shoreline, rivers, rail, roads) for the candidate area; the sheet's linework as a mask; numpy, OpenCV, shapely
---
When names fail but a long distinctive line is on the sheet (a coastline, a river with its bends, a railway, a
main road, a parish boundary), the line's shape places the sheet. Extract the line from the sheet as a mask or a
skeleton (by colour for water and rail, by edge for roads); render the reference class as a distance transform on a
metric grid over the candidate area; sweep rotation and scale (coarse first, fine round the peaks), and for each
pose translate the sheet's line over the distance transform and score the mean distance of its points (chamfer);
refine the best poses by iterative closest point between the sheet's line points and the reference polylines; fit
the similarity or affine. Two guards: a chamfer score is only meaningful against its chance level, so score the
same pose shifted by a few hundred metres and require a margin; and a straight line matches everywhere, so require
the matched line to have curvature (bends, junctions) or use two lines of different classes. Coastlines reclaimed
and rivers straightened since the survey are outliers to tolerate, not evidence against. This matcher needs no
text and no learned model and runs on a CPU in seconds; it is the method for charts, small-scale maps, cadastral
boundaries and sheets whose only readable thing is water.
