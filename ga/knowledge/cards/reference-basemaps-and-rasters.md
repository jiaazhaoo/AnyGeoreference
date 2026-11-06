---
id: reference-basemaps-and-rasters
kinds: [any]
cues: [grid, landmark]
method: what to render or load as the structure to match against, and when a georeferenced raster beats vectors
tags: [base map, vector tiles, Zoomstack, OSM, Natural Earth, GSHHG shoreline, parcel layer, building footprints, georeferenced raster, topoView, NLS tiles, Rumsey, render style]
see: [matcher-render-and-correlate, matcher-map-to-map-editions, family-structure-only, reference-overview]
primitives: [reference_render, osm_reference]
---
Vectors to render: roads, rail, water, buildings and parcels from national open sets or OSM at town scale; coastline
from a global shoreline dataset and borders and rivers from a 1:10 million vector set at small scale; cadastral
parcels and building footprints at large scale. Render in the sheet's language: the same line widths in pixels, the
same classes (a 1900 map shows no motorways, render none), black on white, on a metric grid at the sheet's metres per
pixel. Rasters already georeferenced: an archive's older or newer edition of the same series (national library tile
services, the USGS historical topographic collection, large digitised collections with IIIF), a modern orthophoto
for photographs, a topographic raster for anything drawn from it. Map-to-map in the same symbology is the easiest
match: generic feature matchers work, and the georeference is inherited with the archive's stated accuracy as a
bias. Choose by the sheet: text-rich town sheets want names not rasters; structure-only sheets want the layer their
structure is (roads for a road map, shoreline for a chart, parcels for a cadastre); photographs want orthophotos.
Keep every rendered reference with its bounding box, CRS and resolution next to the match it served, so the
evidence can be re-drawn.
