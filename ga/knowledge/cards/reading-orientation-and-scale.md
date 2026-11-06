---
id: reading-orientation-and-scale
kinds: [any]
cues: [arrow, scale, grid, text]
method: get rotation and metres per pixel from the sheet itself before matching; they bound every sweep
tags: [north arrow, rotation, scale bar, metres per pixel, mpp, representative fraction, grid interval, text orientation, known sizes]
see: [reading-marginalia, failure-rotation-and-mirror, transforms-choice-and-gcps]
---
Rotation: a north arrow (read its angle, and which north it shows), the graticule or grid lines (their angle is the
rotation exactly), the text direction (most labels are written to be read with north up; a sheet whose labels all
run at 90 degrees is a rotated scan), the sheet's long edge convention (national series are landscape or portrait by
rule). Without any of these, the matcher sweeps rotation; with one of them the sweep is a check of +-10 degrees. Scale:
a bar (pixel length over stated length, the most direct), a representative fraction (needs the scan's dots per inch:
300 dpi at 1:10,000 is 0.847 m per pixel), a grid interval (1 km squares N pixels apart), a known feature (a
standard-gauge railway is 1.4 m, a two-lane road 6-7 m, a terraced house frontage 4-6 m, a football pitch 100 m,
a graticule minute of latitude 1,852 m). Expected ranges by family: planning drawings 0.002-2 m/px, town plans
0.02-5 m/px, topographic sheets 1-30 m/px, small-scale maps 100-5,000 m/px; a fit outside the family's range is a
degenerate fit, not a discovery. Scan resolution is in the file's metadata when the archive kept it; a scan
resampled to a fixed width has lost it, and then only the bar or the grid interval gives the scale.
