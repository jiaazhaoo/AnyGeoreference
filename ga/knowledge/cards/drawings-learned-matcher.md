---
id: drawings-learned-matcher
kinds: [planning_drawing, raster_no_text]
cues: [road]
method: learned image matcher (LoFTR-family) in a sliding window over base-map tiles round a seed
---
A learned matcher compares the drawing with rendered base-map tiles round a seed point at several scales and
rotations; the seed comes from the gazetteer or an address, rotation from a north arrow if read, scale from a scale
bar or legend if read. Its own score is not a safe gate: on ten graded drawings a score of 50 accepted a placement
736 m off; with the address point inside the footprint as a second family it accepted two, both right. Expect 1 to 7
minutes a sheet on a GPU at 100 windows; CPU runs with 40 windows give scores under the bar and are only a smoke test.
