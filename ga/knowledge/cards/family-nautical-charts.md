---
id: family-nautical-charts
kinds: [historical_map]
cues: [grid, place, landmark, scale]
method: charts carry a graticule in the border and a Mercator projection; coastline shape is the structure to match
tags: [nautical chart, admiralty, hydrographic, soundings, compass rose, Mercator, chart datum, harbour plan, coastline]
see: [geodesy-projections-identify, matcher-polyline-shape, family-atlas-pages-insets, geodesy-datums-and-shifts]
---
Nautical charts print latitude and longitude scales along the borders (subdivided in minutes and tenths), a compass
rose with magnetic variation and its date, soundings, the coastline, lights, and often harbour plans as insets at a
larger scale. Coastal charts are Mercator: meridians equally spaced, parallels spreading poleward, so a polynomial in
lon/lat over a large sheet bends; fit in the Mercator plane (project the control points with the chart's own
projection, fit a similarity or affine there) and convert, or use a TPS when the printed graticule shows the
distortion. The horizontal datum of older charts is local (an observatory, a named station) and offsets of a few
hundred metres against WGS84 are normal; modern charts state the datum and the shift to WGS84 in the title block.
With no readable border, the coastline is the structure: extract the land/water boundary and match it as a polyline
to a global shoreline dataset after a rotation-and-scale sweep; shoreline reclaimed since the survey (docks, airports,
polders) breaks local matches, so match the long rocky stretches and let the reclaimed ones be outliers. Insets must
be cut out and placed separately; the compass rose is not a north arrow for the whole chart on old sheets where the
rose is magnetic.
