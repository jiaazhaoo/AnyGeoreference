---
id: matcher-sheet-index
kinds: [historical_map]
cues: [text]
method: a sheet number of a known series computes the bounds; the cheapest matcher, still to be verified
tags: [sheet index, sheet number, series, quad, numbering scheme, bounds from name, lookup table]
see: [family-grid-and-series-sheets, family-historic-gb-series, verify-catalogue]
primitives: [sheet_index_lookup]
buildable: yes
effort: hours per series: a function from the printed number to the corner coordinates, plus the series' projection
ingredients: the series' numbering rule or a published corner list; the reader's sheet-number cue; pyproj for the series' projection
---
Numbering schemes are arithmetic: a degree-square letter and a one-inch number give a 15' x 15' box; a grid-square
name gives a south-west corner and a size; a USGS quad name and series give the corners from a public index; a
TK25 four-digit number gives row and column; County Series sheet corners come from a published list per county.
Implementation: a function per series from the parsed sheet number to four corners in the series' CRS, a parser
for the ways the number is printed (53K/4, 53 K/4, 53-K-4), and a table for the schemes that are lists rather than
rules. The result is a Hypothesis with the sheet rectangle mapped to the image rectangle (a four-point affine),
scored low until verified, because the file is not always the sheet in its name, the image includes the collar,
and editions shift corners. Verify by reading the corner values on the sheet (a different family: the printed
numbers against the computed ones) or by structure. A sheet-number read by the model but belonging to no known
scheme is a cue to record, not a placement.
