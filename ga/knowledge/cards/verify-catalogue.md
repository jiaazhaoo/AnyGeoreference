---
id: verify-catalogue
kinds: [any]
cues: []
method: the verification checks, what each is independent of, and how each one fools you
tags: [verification, checks, overlay, address inside, places inside, cross matcher, edition, neighbour sheet, scale sanity, north sanity, archive bounds, user control points, false positive]
see: [verify-evidence-families, verify-overlay-dense-networks, verify-neighbour-sheets, verify-address-in-footprint, verify-places-in-footprint]
primitives: [residual_check, overlay_agreement, hypothesis_agreement, address_in_footprint, places_in_footprint, cross_edition_agreement]
---
Residual and inlier ratio: self-consistency; fooled by a consistent misread (one line off, wrong town with the
same street names). Overlay agreement (sheet linework near reference linework): independent of text; fooled by
dense networks where anything is near a road, so compare with a shifted pose. Address point inside the footprint:
independent of structure and of the reader's labels when it comes from the record; fooled when the record's
address is itself wrong or when the footprint is large enough to contain it by chance (a 2 km footprint always
contains the address). Place names inside the footprint: independent of a road fit; fooled by common names, so use
names the fit did not consume and weight rare ones. Cross-matcher agreement (two matchers of different kinds within
a tolerance): strong, because their failure modes differ; fooled only when both used the same wrong seed. Another
edition of the sheet: strong; fooled by the archive's own mistake. Neighbour-sheet continuity: strong, available
only in batches. Scale and north sanity (metres per pixel in the family's range, rotation near the read arrow):
cheap necessary conditions, never sufficient. Archive bounds: an external authority with a datum bias. User control
points: the top of the ranking. A policy row names which of these it requires and its measured accepted-wrong rate;
a row that relies on one family alone is the row that fails.
