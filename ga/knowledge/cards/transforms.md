---
id: transforms
kinds: [any]
cues: [grid]
method: which transform to fit
---
Similarity (4 dof) for a flat scan with a known scale; affine (6) when the scanner stretched one axis; 2nd-order
polynomial (12) for paper stretch and sheet-wide distortion, which needs at least a dozen well-spread control points
and is checked by leave-one-window-out residuals. Never fit a polynomial to points on one edge. Report residuals in
metres: convert degrees with 111320 cos(lat) and 110574.
