---
id: operate-delivery-contents
kinds: [any]
cues: []
method: what a finished delivery contains so that someone else can reproduce, check and reuse it
tags: [delivery, contents, transform, GCPs, residuals, footprint, evidence table, probability, trace, cost, reproducible]
see: [geodesy-crs-and-outputs, verify-acceptance-policy, operate-abstention-reasons]
---
Per sheet: the decision (accepted, review, abstained) with its typed reason and its calibrated probability; the
transform (model, parameters, CRS by EPSG code, datum and shift applied) and the control points with per-point
residuals and the cue each came from; the footprint polygon and, on drawings, the site polygon; the evidence table
(each check, its value, its family, its source kind: deterministic, model, person, record); the trace (every tool
run, in order, with its inputs' digests, outputs, time and cost); the references used (source, version, bounding
box, licence); the orientation and cropping operations applied to the raw scan; the reader's cues as read, with
boxes. Per batch: the plan as written, the recipe version frozen, the pilot's result against truth, the
evaluation (placed right, placed wrong, abstained by reason, calibration, cost), and what was built. Nothing in a
public delivery carries licensed extracts or personal data; everything in a private one is reproducible from the
trace. A delivery without residuals, evidence and trace is a guess with a map on it.
