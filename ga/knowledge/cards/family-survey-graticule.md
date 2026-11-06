---
id: family-survey-graticule
kinds: [historical_map]
cues: [grid]
method: printed graticule or corner coordinates as ground control points, polynomial fit
tags: [survey sheet, topographic, one-inch, quarter-inch, neatline, graticule, corner coordinates, degrees minutes]
see: [matcher-graticule-corners, geodesy-datums-and-shifts, failure-one-line-off, family-grid-and-series-sheets]
primitives: [graticule_frame, graticule_frame_bounds, control_point_fit, residual_check]
---
Survey-series sheets (national topographic series at 1:25,000 to 1:250,000, colonial one-inch and quarter-inch
series, military sheets) print their neatline coordinates in the corners and a graticule every few minutes; every
intersection is a control point for free (49 on a 30' half-degree sheet at 5' intervals). Read the corner values
(degrees and minutes, sometimes seconds; the hemisphere letters; the interval between ticks), find the neatline
and the tick marks as lines in the image, intersect them, and fit a 2nd-order polynomial sheet px -> lon/lat; the
residual at the nodes should be tens of metres at 1:63,360. Then convert to the CRS the user wants. Failure modes:
the frame reader takes the second graticule line for the neatline and every node shifts by one interval (9 km at
5') while the residual stays small; a raster already resampled to degrees has a 1:1 pixel aspect, a paper scan has
cos(lat) squeezing longitude; the printed coordinates sit on the survey's datum (Everest 1830 in South Asia, OSGB36
in Britain, NAD27 in the USA), expect tens to hundreds of metres against WGS84 references unless shifted. Verify with
an independent family: structure against a modern road or water layer, another edition of the same sheet, or the
neighbouring sheet's edge. A sheet number of a known series gives the bounds without reading anything: check them
against the read corners, a disagreement is a misread or a different series.
