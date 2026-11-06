---
id: transforms-paper-and-scan-distortion
kinds: [historical_map, planning_drawing]
cues: [grid]
method: paper shrinks, folds and curls, scanners skew and tile; cut to the neatline, dewarp, and let the model match the distortion
tags: [paper shrinkage, anisotropic, fold, curl, scanner skew, tiled scan, mosaic seam, microfiche, dewarp, neatline crop, photographed map]
see: [transforms-choice-and-gcps, family-atlas-pages-insets, failure-rotation-and-mirror]
---
Paper maps shrink 0.5-2% with age and humidity, more along the grain than across it, so a 60 cm sheet is off by up
to a centimetre at the far edge: a similarity leaves a gradient, an affine absorbs the anisotropy, a polynomial
absorbs the fold. Folded sheets scanned flat have steps at the folds; sheets scanned in tiles and stitched have seams
with small offsets; large sheets photographed rather than scanned have lens distortion and keystone (a projective
component); microfiche frames are negatives, sometimes mirrored, with the frame edge in the image; curled edges in
a flatbed scan lose focus and scale. Practice: crop to the neatline before anything else so the collar does not
feed the matcher; estimate the scale on both axes separately and report the aspect; when residuals show a fold or
a seam, fit piecewise (one model per region) or a thin plate spline with points on both sides of the seam; when
the distortion is a lens, fit projective first; keep the raw scan and record every geometric operation applied so the
chain from raw pixels to CRS is reproducible. A distortion model is chosen by the residual pattern, never in
advance, and the simpler model's residuals are reported next to the chosen one's.
