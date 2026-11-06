---
id: family-grid-and-series-sheets
kinds: [historical_map, street_map]
cues: [grid, text]
method: grid figures on the margins or the sheet number of a known series give the bounds before any matching
tags: [national grid, UTM, MGRS, sheet number, sheet index, quad, Blattnummer, County Series, six-inch, 25-inch]
see: [matcher-sheet-index, matcher-grid-labels, family-survey-graticule, geodesy-projections-identify]
primitives: [sheet_index_lookup, grid_figures]
---
Map series are numbered, and the number is a location. Great Britain, National Grid series: 1:10,000 sheets are
named by the 10 km square and quarter (SK 36 NE), 1:2,500 by the 1 km square (SK 3665), 1:1,250 by its quarter
(SK 3665 NE); the name is the south-west corner and the size, no reading of coordinates needed. Great Britain, County
Series (1840s-1940s): six-inch (1:10,560) and 25-inch (1:2,500) sheets numbered per county (Yorkshire CCXCIV.10),
on Cassini projections with a meridian per county or county group, so a County Series sheet is not a simple shift
from the National Grid; the published county sheet corners (lists exist per county) give the bounds, and a
transformation per county is needed. USA: USGS quadrangles, 7.5' at 1:24,000, 15' at 1:62,500, 30' at 1:125,000,
30'x60' at 1:100,000, 1x2 degrees at 1:250,000; the quad name and series give the corners exactly. South Asia,
Survey of India: 4-degree sheets numbered 1-136, each split into 16 degree squares lettered A-P (quarter-inch),
each into 16 one-inch sheets of 15'x15' numbered 1-16 (53K/4), half-inch sheets of 30'x30' as NE/NW/SE/SW.
Germany: TK25 Blattnummer, four digits, row from the north then column, sheets 10' x 6'. France: IGN 1:25,000 by
Lambert grid. Grid figures printed on the margins (eastings and northings in km, UTM/MGRS zone and 100 km letters)
are control points like a graticule but in a projected CRS: fit directly in that CRS, and read the zone, it is not
on the sheet twice. The index lookup is the cheapest matcher there is and must still be verified: the sheet in the
file is not always the sheet in the catalogue, and editions move corners by survey revisions.
