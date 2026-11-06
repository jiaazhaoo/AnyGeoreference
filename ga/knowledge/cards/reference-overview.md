---
id: reference-overview
kinds: [any]
cues: [road, place, number, grid]
method: which reference to retrieve for which cue, and how to render it
tags: [reference data, OSM, Ordnance Survey, Overpass, gazetteer, address register, base map, render, cache]
see: [reference-gazetteers, reference-road-networks, reference-addresses, reference-basemaps-and-rasters, reference-historic-epoch, reference-licensing-and-privacy]
primitives: [gazetteer_search, place_lookup, osm_reference, reference_render]
---
Each cue kind has a reference that turns it into a position. Place names: a gazetteer (national names datasets,
GeoNames, Wikidata, a historical transcription for old sheets). Road names: a named road-centreline network (a
national open roads layer, OSM highways by Overpass). House numbers: an address register (points per address, with
street and number). Grid figures and sheet numbers: the series index, computed, no download. Structure (roads,
rail, water, buildings, coastline, parcels): vector layers to render (national open vector sets, OSM, a global
shoreline, a cadastral parcel layer) or an already-georeferenced raster of the same series. Overpass mirrors fail
often: retry across mirrors, cache by bounding box and query hash, never let one 502 fail a batch. Render references
black-on-white at the image's metric resolution with line widths matched to the scan, and paint out printed
graticules and grid lines on the sheet before structure matching because the reference has none. The slow-changing
skeleton (railways, canals, rivers, main roads, churches, settlements) matches maps a century old; the fast-changing
skin (suburbs, bypasses, demolished streets, reclaimed shore) does not, and a matcher that weights them equally
fails on old sheets. Every reference answer is cached by request hash so a rerun is free and reproducible.
