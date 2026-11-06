---
id: transforms-choice-and-gcps
kinds: [any]
cues: [grid]
method: which transform to fit, with how many control points, spread how; the sheet's scale sets the residual bar
tags: [similarity, affine, projective, homography, polynomial, second order, third order, thin plate spline, TPS, rubber sheet, GCP minimum, point spread, conditioning, RANSAC, leverage]
see: [transforms-residual-diagnostics, transforms-paper-and-scan-distortion, truth-tolerance-by-scale, geodesy-projections-identify]
primitives: [control_point_fit, text_anchor_fit]
---
Models and their minimum control points: similarity (scale, rotation, translation; 4 parameters, 2 points) for a
flat scan of a known-scale sheet; affine (6, 3 points) when the scanner or the paper stretched one axis; projective
(8, 4 points) for a vertical photograph of flat ground or a sheet photographed at an angle; 2nd-order polynomial
(12, 6 points) for paper-wide distortion and small projection effects; 3rd-order (20, 10 points) rarely, it bends
between points; thin plate spline (exact at every point, 3 minimum, in practice 10 or more well spread) for local
warps, with no residual at the nodes so its error is measured by leave-one-out. Use the simplest model that brings
the residual under the bar, and the bar is 0.5 mm at map scale (the cartographic standard): 1.25 m at 1:2,500, 5 m at
1:10,000, 32 m at 1:63,360. Spread: the convex hull of the points should cover most of the sheet; a polynomial fitted
to points along one edge extrapolates wildly, and a model with more parameters than well-spread points is noise.
Condition the solve: normalise pixel and CRS coordinates to the unit box before least squares, scale back after.
Robustness: RANSAC with a threshold in metres (a few pixels at the sheet's metres per pixel), then refit on inliers,
report inliers over total. Bound the result: metres per pixel in the family's range, rotation near the north arrow,
aspect ratio near 1 (a paper scan), determinant positive unless mirroring was expected. A fit is a Hypothesis with
its residuals, never a fact.
