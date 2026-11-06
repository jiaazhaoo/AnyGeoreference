---
id: family-atlas-pages-insets
kinds: [historical_map, raster_no_text]
cues: [grid, text, scale]
method: a page with several frames is several sheets; find the neatlines first and georeference each frame on its own
tags: [atlas, inset, neatline, multiple frames, microfiche jacket, mosaic page, collar, title block, split]
see: [reading-marginalia, family-nautical-charts, failure-modes-catalogue]
---
Atlas pages, chart insets, microfiche jackets and scanned mosaics hold more than one map frame per image: a main map
with a harbour inset at ten times the scale, a page of four county maps, a jacket of eight negatives, a plan with a
location inset at 1:10,000 beside a site plan at 1:500. One transform for the page is wrong for every frame. Detect
neatlines (long straight dark lines closing a rectangle, or the edge of the map colour against the collar), cut
each frame out as its own Sheet with its own id and offset, read each frame's own scale and labels, and georeference
each; the location inset's result is a candidate area for the site plan, not its transform. Negatives (microfiche)
are inverted and sometimes mirrored: invert, and test mirroring during the coarse stage. The collar outside the
neatline (title, legend, notes, sheet number, edition) is read for retrieval and metadata and never used as a
control point. A page delivers a list of placements, one per frame, with the frame's pixel rectangle on the page.
