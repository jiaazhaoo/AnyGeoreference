---
id: graticule-sheets
kinds: [historical_map]
cues: [grid]
method: printed graticule or corner coordinates as ground control points, polynomial fit
---
Survey-series sheets print their neatline coordinates and a graticule every few minutes; every intersection is a
control point for free (49 on a 30' quarter sheet). Fit a 2nd-order polynomial sheet px -> lon/lat; the residual at the
nodes should be tens of metres. Failure modes: the frame reader takes the second graticule line for the neatline and
every node shifts by one interval (9 km) while the residual stays small; a raster already resampled to degrees has a
1:1 pixel aspect, a paper scan has cos(lat) squeezing longitude. Printed coordinates sit on the survey's datum
(Everest 1830 in South Asia): expect a few hundred metres against WGS84 references. Verify with an independent
family: structure against OSM, or another edition of the same sheet.
