---
id: geodesy-projections-identify
kinds: [historical_map]
cues: [grid]
method: identify the projection from the graticule's shape and fit in that plane; an affine in lon/lat only holds for small sheets
tags: [projection, Mercator, Cassini, Transverse Mercator, Lambert conformal conic, Albers, Bonne, polyconic, equirectangular, Mollweide, graticule shape, pyproj]
see: [family-small-scale-thematic, family-nautical-charts, transforms-choice-and-gcps, geodesy-datums-and-shifts]
---
The graticule's shape names the projection. Straight meridians and straight parallels, both equally spaced:
equirectangular (plate carree). Straight equally spaced meridians, parallels spreading toward the poles: Mercator
(charts, world maps). Straight meridians converging to a point with parallels as concentric arcs: a conic (Lambert
conformal: national series in France, the USA state planes; Albers: thematic maps of large countries). Curved
meridians with concentric arc parallels and a straight central meridian: Bonne (19th-century national surveys of
France, Belgium, the Netherlands, Switzerland) or polyconic (USGS before 1950s, India's older series). Straight
central meridian, slightly curved others on a sheet-sized area: Cassini (Ordnance Survey County Series, Prussian
and other 19th-century cadastral surveys) or Transverse Mercator (every modern national grid, UTM). Ellipse or oval
outline: a world projection. Rule: for a sheet under about 50 km across, a 2nd-order polynomial in lon/lat absorbs
the projection; above that, project the control points with the identified projection (the parameters are on the
sheet or in the series documentation: central meridian, standard parallels, origin) and fit a similarity or affine
in projected metres, then express the transform as a chain. A fit whose residuals grow smoothly from the centre to
the edges is a projection mismatch, not a bad reading. State the projection used in the delivery.
