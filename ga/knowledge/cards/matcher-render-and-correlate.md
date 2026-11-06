---
id: matcher-render-and-correlate
kinds: [raster_no_text, historical_map]
cues: []
method: render the reference in the sheet's own style and correlate (edge NCC, phase correlation, mutual information) over the sweep
tags: [template matching, normalised cross-correlation, phase correlation, mutual information, render style, edge map, same-style match, FFT]
see: [matcher-learned-image, matcher-polyline-shape, reference-basemaps-and-rasters, family-structure-only]
buildable: yes
effort: half a day: a style-matched render, edge maps on both sides, FFT correlation per rotation and scale, chance-level check
ingredients: vector layers for the candidate area (roads, rail, water, buildings); the sheet's metres per pixel or a scale sweep; numpy, OpenCV
---
When the sheet and the reference can be made to look alike, correlation beats learned matching for cost: render
the reference layers in the sheet's line widths and classes, take edge maps of both, and correlate (normalised
cross-correlation by FFT over the translation space, once per rotation and scale in the sweep); the peak's
sharpness against the second peak is the confidence, and the same pose shifted gives the chance level. Phase
correlation finds translation at sub-pixel precision when scale and rotation are already known (a sheet with a
north arrow and a scale bar). Mutual information handles the cases where edges do not line up but intensities
co-vary (a photograph against a map, a shaded relief against contours), the classic cross-modal measure from
medical registration. Correlation is global: one sheet, one pose, which is right for undistorted scans and wrong
for folded or stretched ones; use it to find the pose, then refine locally with control points. It is also the
method for a same-series edition already georeferenced: two sheets of the same symbology correlate directly without
any rendering, and the older edition's georeference is inherited with the archive's bias stated.
