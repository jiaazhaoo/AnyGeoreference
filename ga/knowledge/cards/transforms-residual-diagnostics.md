---
id: transforms-residual-diagnostics
kinds: [any]
cues: [grid]
method: the pattern of residuals names the fault: uniform, gradient, rotational, one outlier, edge growth
tags: [residual, RMSE, outlier, uniform offset, gradient, leave one out, leave one window out, diagnostics, pattern]
see: [transforms-choice-and-gcps, geodesy-datums-and-shifts, failure-one-line-off, failure-modes-catalogue]
primitives: [residual_check, hypothesis_agreement]
---
Look at the residual vectors, not only their RMS. All the same direction and length: a datum shift, a misindexed
grid (every point one interval off, the fit still perfect), or a wrong reference epoch. Growing linearly along one
axis: wrong scale or a stretched axis, fit affine instead of similarity. Rotating about the centre: a rotation
error, usually a north arrow read for the wrong north. One large, the rest small: one misread point, drop it and
refit, then check that the dropped point's reading was a plausible digit swap. Growing smoothly from the centre to
the edges: projection or lens, fit in the projection plane or go up one polynomial order. Random and all large:
the points are not what they were read as (wrong sheet, wrong town), or the sheet is schematic. Report residuals
in metres (convert degrees with 111,320 cos(lat) for longitude and 110,574 for latitude), per point, with the
source cue of each point so a person can see which label misled. Cross-check by leaving out one window of the sheet
(not one point: neighbouring points share the fault) and predicting it. A small residual proves the points agree
with each other; only a family that did not feed the fit (an address inside, an overlay, a neighbour sheet, an
archive bound) proves they agree with the Earth.
