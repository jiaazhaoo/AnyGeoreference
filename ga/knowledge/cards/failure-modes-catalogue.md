---
id: failure-modes-catalogue
kinds: [any]
cues: []
method: symptom, cause, check: the faults a professional has seen before
tags: [failure modes, symptom, cause, check, one line off, wrong town, datum, degenerate, inset, rotation, mirror, unit, digits, hallucination, renamed, dense network]
see: [failure-one-line-off, failure-rotation-and-mirror, transforms-residual-diagnostics, reading-hallucination-guard]
---
Perfect residual, placement one grid interval off: the frame reader took the second line for the neatline; check
the count of lines found against the count expected, verify with another family. Good fit of all street names,
wrong town: common street names; locate by junction votes first and require a rare name or a place name inside.
Uniform offset of 50-500 m: datum; shift and keep both. Offset growing to the edges: projection; fit in the
projection plane. Scale off by a round factor (1.6, 3.28, 20): units (miles, feet, chains); read the bar's unit.
Scale near zero or metres per pixel absurd: degenerate fit from collinear or duplicated points; bound the scale and
require spread. Fit on the inset, not the map: several frames per page; cut frames first. Rotated 90 or 180, or
mirrored: scan orientation or negative; test the four rotations and mirror in the coarse stage, text direction
decides. Labels that fit nowhere: hallucinated or misread names; require a second reader or a gazetteer hit before
anchoring; digits 3/8, 1/7, 0/6 swap. Half the labels fit, half do not, on an old sheet: renamed and removed
streets; weight the persistent classes and widen the tolerance. High overlay score at a wrong pose: dense network;
margin over shifted poses. Learned matcher confident and wrong: its score is self-consistency; demand the address
or a place inside. Right transform, wrong site polygon: the ring read is the neighbour's; check the address
against the ring, not the footprint. Reference 502 or empty: a mirror failed or the bounding box was in the wrong
CRS; retry, cache, check the box. Nothing placed on a sheet with no cues: not a failure; an abstention with its
reason is the right answer.
