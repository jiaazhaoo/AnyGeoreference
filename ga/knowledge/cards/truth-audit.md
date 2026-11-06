---
id: truth-audit
kinds: [any]
cues: []
method: truth can be wrong; disagreement with it triggers an audit, never a silent fail or a silent pass
tags: [truth audit, wrong truth, archive bias, label version, digest, disagreement, graded polygon, reviewer saw]
see: [truth-sources, geodesy-datums-and-shifts, verify-acceptance-policy]
---
Every truth source has its own error: archive georeferences keep printed datums and sometimes mislabel sheets;
graded client polygons were graded against a particular drawing version and a particular base map; a reviewer's
verdict is about the polygon the reviewer saw, which may not be the polygon now in the file; gazetteer entries carry
their own coordinate accuracy (a village centroid, not the church); user control points are clicked with a pixel
or two of slack. So a placement that disagrees with truth by exactly the datum vector confirms the placement and
flags the truth; a disagreement on one sheet of a tiling batch where the neighbours agree flags that sheet's truth;
a verdict bound to an older artefact digest is stale and is excluded, not counted as a miss. Practice: bind every
truth record to the digest of the artefact it judged and to its source rank; when a benchmark case fails, the
first question is whether the truth or the placement is wrong, answered by a third source; keep the audit's
outcome as a new truth record with its own source and time, never by editing the old one.
