---
id: matcher-learned-image
kinds: [planning_drawing, raster_no_text, historical_map]
cues: [road]
method: learned image matcher (LoFTR-family, modality-invariant training) in a sliding window over reference tiles round a seed
tags: [learned matcher, LoFTR, SuperPoint, SuperGlue, LightGlue, MINIMA, XoFTR, RoMa, DKM, cross-modal, sliding window, GPU, seed, windows, score threshold]
see: [family-planning-drawings, family-structure-only, matcher-render-and-correlate, literature-image-matching, verify-address-in-footprint]
primitives: [plan_minima_match, structure_match, structure_match_orb]
buildable: yes
effort: in the library (two bindings); a new binding of another matcher is hours with weights on this machine
ingredients: a seed point and radius; rendered reference tiles at several scales and rotations; a matcher checkpoint (modality-invariant LoFTR works across drawing and render); a GPU for more than a smoke test
---
Classical detectors (SIFT, ORB) match a photo to a photo and fail across modalities: a hand-drawn plan against a
rendered base map, an engraved sheet against a modern vector render, a photograph against a map share no local
appearance. Transformer matchers trained on cross-modal pairs do: a LoFTR-family model trained with a
modality-invariant data engine matches a drawing to a render well enough to place half of a graded set, and the
same model matches old to new editions of a series easily. Use it as a window search: seed from the gazetteer or
the address, render tiles round the seed at the scales and rotations the reading allows (a north arrow cuts the
rotations to one, a scale bar the scales to one), run the matcher per tile, fit a similarity by RANSAC on the
matches, and keep the window with the most inliers. Its own score is not a safe gate: on ten graded drawings a score
of 50 accepted a placement 736 m off; with the address point inside the footprint as a second family it accepted
two, both right. Expect 1 to 7 minutes a sheet on a GPU at 100 windows; CPU runs with 40 windows give scores under
the bar and are only a smoke test. Paint out text and the graticule before matching; they are not in the render.
Dense matchers (RoMa, DKM) give more matches on texture-poor drawings at more cost; a lighter matcher with learned
keypoints (SuperPoint plus LightGlue) is faster on map-to-map in the same style.
