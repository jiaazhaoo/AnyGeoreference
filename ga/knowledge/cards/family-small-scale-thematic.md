---
id: family-small-scale-thematic
kinds: [historical_map]
cues: [grid, place, text]
method: country and continent maps place by projection identification, graticule and coastline or border shape
tags: [small scale, atlas, thematic, country map, continent, projection, Natural Earth, borders, coastline, km tolerance]
see: [geodesy-projections-identify, matcher-polyline-shape, matcher-toponym-constellation, truth-tolerance-by-scale]
---
At 1:1,000,000 and smaller the Earth's curvature is the first problem: no affine fits a continent. Identify the
projection from the graticule (straight equally spaced meridians and parallels: equirectangular; parallels spreading
poleward: Mercator; straight converging meridians with circular parallels: conic; curved meridians with circular
parallels: Bonne or pseudo-conic; everything curved: a world projection such as Mollweide or Winkel). Fit the
transform in the projection's own plane: project the control points (graticule intersections, or coastline and
border vertices from a global dataset) with that projection, fit a similarity or affine in projected metres, then
express the result as a chain: sheet px -> projected plane -> lon/lat. Where the projection cannot be named, a thin
plate spline over many well-spread control points approximates it, at the price of no residual check at the nodes
(use leave-one-out). Coastline and country borders are the structure; borders move, so prefer coastlines and
rivers for anything older than the last border change in the area. Toponyms place these maps too: a constellation
of five or six capital cities is unambiguous worldwide. Tolerance is kilometres: 0.5 mm on a 1:5,000,000 map is
2.5 km, and the map was never better than that.
