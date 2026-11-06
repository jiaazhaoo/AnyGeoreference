---
id: truth-tolerance-by-scale
kinds: [any]
cues: [scale]
method: a placement is right when it is within what the map itself can give: 0.5 mm at map scale, plus the task's own bar
tags: [tolerance, accuracy, 0.5 mm rule, map scale, RMSE, CE90, CE95, NMAS, ASPRS, task tolerance, right for the task]
see: [transforms-choice-and-gcps, verify-acceptance-policy, literature-accuracy-standards]
---
The map was drawn to about 0.5 mm, so that is the floor of what "right" can mean: 0.25 m at 1:500, 0.6 m at 1:1,250,
1.25 m at 1:2,500, 5.3 m at 1:10,560, 12.5 m at 1:25,000, 32 m at 1:63,360, 125 m at 1:250,000, 500 m at
1:1,000,000, 2.5 km at 1:5,000,000. Report accuracy as RMSE over check points the fit did not use and, when a
confidence level is asked for, CE90 (1.52 x RMSE) or CE95 (1.73 x RMSE) under the circular assumption. The task
adds its own bar, which may be looser or tighter than the map's: a site polygon that must fall in the right parcel
needs about 5 m regardless of the drawing's scale; a sheet that must be the right sheet of a series needs one
interval; a historical change study at 1:63,360 is happy with 50 m. The policy's tolerance is the task's bar, the
map's floor is the sanity limit below which a claimed accuracy is fiction. Datum shifts (100 m) and projection
mismatches (growing to the edges) are errors larger than any of these and must be removed, not tolerated.
