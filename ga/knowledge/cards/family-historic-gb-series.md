---
id: family-historic-gb-series
kinds: [historical_map]
cues: [grid, road, place, text]
method: British historic series have published corners, transcribed labels and georeferenced editions to lean on
tags: [Ordnance Survey, County Series, six-inch, 25-inch, one-inch, Old Series, New Series, Seventh Series, NLS, GB1900, Cassini, National Grid]
see: [family-grid-and-series-sheets, reference-gazetteers, matcher-map-to-map-editions, geodesy-datums-and-shifts]
---
Ordnance Survey series are the best-documented case. One-inch (1:63,360) Old Series 1805-1874 on a Cassini projection
from Greenwich; New Series and Popular Edition on Cassini (Delamere origin), Seventh Series (1952-) on the
Transverse Mercator National Grid. Six-inch (1:10,560) and 25-inch (1:2,500) County Series 1840s-1940s on Cassini
with county or county-group origins, sheet numbers per county; the National Grid 1:10,000, 1:2,500 and 1:1,250
series after 1945 named by grid square. Town plans at 1:500 and 1:1,056 for larger towns 1850s-1890s. What this
gives the georeferencer: corner coordinates per County Series sheet exist in published lists; a complete set of
six-inch and 25-inch sheets is already georeferenced and served as tiles by the national library of Scotland, so a
sheet of the same series can be matched map-to-map (same symbology, same scale, the easiest match there is) and the
tile's georeference inherited; the names printed on the six-inch 1888-1913 edition were transcribed with
coordinates by a crowd project (GB1900, 2.5 million labels), which is the gazetteer to use for any Victorian or
Edwardian sheet, modern gazetteers lack the farms, mills and field names. Printed lat/lon on these sheets is on
OSGB36 (or earlier, on the Old Series); the National Grid itself is OSGB36 and needs no shift when delivered in
EPSG:27700.
