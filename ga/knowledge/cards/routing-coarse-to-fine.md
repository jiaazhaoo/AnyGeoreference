---
id: routing-coarse-to-fine
kinds: [any]
cues: [place, road, grid]
method: narrow from the world to the sheet in stages; never run a fine matcher without a candidate area
tags: [hierarchy, candidate area, seed, locate then fit, cost control]
see: [routing-by-cues, operate-cost-and-time, reference-gazetteers]
---
Placement is a funnel. Stage 0, the world: the record (a council, a county, a country), the sheet series, the
language of the labels, the projection of the graticule narrow the search to a region. Stage 1, the town (10 km):
a gazetteer lookup of the place names, the densest cluster of hits across several names (one name is ambiguous,
three names together rarely are). Stage 2, the kilometre: junction votes from street-name pairs, an address point,
a printed grid figure, a sheet index. Stage 3, the metre: a fit, by control points, by label-to-centreline, by a
learned matcher in windows round the stage-2 seed. Stage 4, verification from a family the fit did not use. Each
stage returns a Candidate with a radius; the next stage searches only inside it. Running a learned matcher without a
candidate area means thousands of windows and a best score somewhere wrong; the funnel is what makes a fine matcher
affordable and its best window meaningful. When a stage returns nothing, the funnel stops and says at which stage:
"no candidate area" is a different abstention from "candidate area but no fit".
