---
id: literature-image-matching
kinds: [any]
cues: []
method: which matchers exist, what they were trained on, and where each fails on maps
tags: [literature, SIFT, ORB, SuperPoint, SuperGlue, LightGlue, LoFTR, DKM, RoMa, XoFTR, MINIMA, MapGlue, RIFT, CFOG, mutual information, cross-modal]
see: [matcher-learned-image, matcher-render-and-correlate, matcher-polyline-shape]
---
Handcrafted local features (SIFT 2004, ORB 2011) match the same scene under viewpoint and lighting change and fail
across modalities; on a drawing against a render they return nothing usable, measured. Learned keypoints and
matchers (SuperPoint 2018 with SuperGlue 2020 or LightGlue 2023) are fast and work map-to-map in one style.
Detector-free transformers (LoFTR 2021) match texture-poor regions densely; dense matchers (DKM 2023, RoMa 2024)
give the most correspondences at the highest cost. Cross-modal training is what makes maps work: XoFTR (2024) for
thermal and visible, MINIMA (2025) with a data engine that generates many modalities from one source so that one
LoFTR-family model matches across drawing, render, photograph and map; a modality-invariant checkpoint is the
binding in the library and it placed half of a graded drawing set. Remote-sensing multimodal matching has its own
line (RIFT 2019 on phase congruency, CFOG 2019 on oriented gradients, MapGlue 2025), useful for photo-to-map.
Classical cross-modal similarity, mutual information (1997), still works where edges do not coincide but intensities
co-vary. All of them produce correspondences, not placements: RANSAC with a metric threshold, a bounded model and a
second evidence family are what turn matches into an accepted transform, and no matcher's own score has proven safe
as a gate on its own.
