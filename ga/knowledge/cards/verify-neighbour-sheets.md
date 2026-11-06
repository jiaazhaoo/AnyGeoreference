---
id: verify-neighbour-sheets
kinds: [historical_map]
cues: [grid, text]
method: adjacent sheets of a series must tile; features must continue across the join; a batch's own second family
tags: [neighbour sheets, adjoining sheets, edge continuity, tiling, batch agreement, series, adjoining diagram]
see: [routing-input-contract, truth-sources, family-grid-and-series-sheets]
buildable: yes
effort: hours: from two placed sheets with known adjacency, the gap or overlap between their footprints and the offset of linework across the shared edge
ingredients: two or more placed sheets of one series with their index positions; the sheets' linework near the edges; shapely, numpy
---
A series tiles the country: sheet 53K/4 shares its east edge with 53K/8, the six-inch sheet XXIII.4 abuts XXIII.5.
Two placed neighbours must meet with no gap or overlap beyond the tolerance for the scale, and a road or river
leaving one must enter the other at the same point. This is an evidence family that no single sheet has and that a
batch of three similar sheets gets for free when they adjoin, which is why three similar sheets are the recommended
input. Implementation: from the index positions decide which pairs adjoin and on which side; compute the gap
between the footprints along the shared edge; sample linework within a margin of the edge on both sheets, transform
to the CRS, and measure the offset between the two sets; agreement within the scale's tolerance is the evidence,
disagreement by one interval on one sheet is the one-line-off read, disagreement by the same vector on all is the
datum. Non-adjoining sheets of the same series still share scale, rotation convention and datum, which is a weaker
agreement to report.
