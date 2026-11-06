---
id: drawings-text-anchors
kinds: [planning_drawing]
cues: [road, number, place]
method: road names and house numbers against an address register, RANSAC similarity
---
Planning drawings carry road names, house numbers and a scale (1:500 to 1:2500). Read the names (a vision model reads
hand lettering OCR misses), find the record's street in a gazetteer to get a candidate area, then match number x road
pairs to address points and fit a similarity by RANSAC; three inliers suffice, eleven of twelve is a strong fit.
Reject fits whose metres-per-pixel fall outside 2 mm to 2 m (a degenerate fit gives scale 0). Verify with the address
point inside the footprint. Sheets without numbers need the learned matcher against the base map; sheets with no
location cue at all (floor plans, setting-out plans, sections) cannot be placed: abstain and say so.
