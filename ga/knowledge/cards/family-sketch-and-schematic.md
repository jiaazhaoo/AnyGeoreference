---
id: family-sketch-and-schematic
kinds: [street_map, historical_map]
cues: [place, road, landmark, text]
method: schematic maps are topologically right and metrically wrong; place by landmarks with a rubber sheet and label the result schematic
tags: [sketch map, schematic, transit map, diagram, tube map, hand-drawn, mental map, topology, TPS, not metric]
see: [transforms-choice-and-gcps, matcher-toponym-constellation, operate-delivery-contents]
---
Transit diagrams, sketch maps in letters and reports, tourist maps, and hand-drawn directions keep the order of
things and the connections, not distances or angles. A similarity fit to such a sheet gives large residuals that are
the drawing's, not a misread's. What is deliverable: the named places and junctions matched to their real positions
(a point list), a thin plate spline through those points that warps the sheet so the names land where they belong
(for display, not measurement), and a note that the product is schematic with the residual of a similarity fit as
the measure of how schematic. Do not deliver a footprint polygon as if it were measured. The reader's job is the
list of named things; the matcher's job is the point list; the policy marks the result "schematic" rather than
accepted or wrong. Where a sketch carries a scale bar and a north arrow, test whether a similarity fits within the
tolerance for its scale before deciding it is schematic.
