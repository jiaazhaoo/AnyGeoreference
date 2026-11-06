# Findings (dated, with the numbers that back them)

Negative and positive results alike; each entry says what was measured, on what, and what changed because of it.

## 2026-11-06

**Reading the graticule is self-consistent even when it is wrong by one line.** On the 1943 edition of one quarter
sheet the frame reader took the second graticule line for the neatline: 49 nodes, 3.0 px fit, 40 m residual at
the nodes, and a placement 9.2 km (one 5' row) south of the archive's. The 1925 edition of the same sheet, read
independently, disagreed with it by 6.7 km; the OSM structure match accepted 0 of its windows. Residual at the
nodes therefore proves consistency, not correctness. Change: the historical-map policy accepts only with a second
evidence family (structure match agreeing, or another edition agreeing); residual alone sends the sheet to review.

**Six sheets under the second-family rule.** Two series, three decades, 49 graticule nodes read on every sheet.
Against the archive's georeference at 100 m: 3 accepted (2 within 65 m of the archive, 1 at 654 m where both of
our matchers agree with each other and disagree with the archive), 3 sent to review (the two one-line-off reads at
9 km, which the rule caught, and one false alarm at 61 m whose two matchers sat 200 m apart). Without the rule all
six were accepted, three of them wrong. Replay: `/data/lab/projects/georeference-anything/soi/bench_soi6_scorecard.json`.

**The archive's own georeference carries the printed-coordinate datum.** On the sheet that was read correctly,
the loop's placement sits 33 m rms from the archive's, and the printed coordinates themselves sit 31 m from it:
the archive reproduces the printed (Everest-datum) coordinates with a small warp. The OSM structure match (168
windows in 40 s on CPU, 84 accepted, 2,698 control points, leave-one-window-out median 38 m) moves the placement
about 88 m from the archive, toward where the features are on OSM. Which of the two is right needs an independent
truth; the archive is not it.

**A generic feature matcher places a road render but not a hand-drawn plan.** ORB + RANSAC against reference roads
placed a rotated, shifted render of a city district to 5–7 m at the corners (overlay 0.85) with a hint 0.5 km off.
On ten real planning drawings with their graded polygons as truth, the same matcher produced no hypothesis on any
case; the text-anchor matcher placed 1 of 10 (8 m from the truth, address inside), the gazetteer found a candidate
area for 9 of 10. The production pipeline's learned matcher (seeded by road names) accepts 6 of those 10. The
generic baseline is the floor, not the method, for drawings.

**Retrieval wants the whole page; matching wants the sheet.** Restricting OCR to the plan crop dropped the
gazetteer's candidate areas from 9 of 10 to 3 of 10; keeping page-wide words for retrieval and on-sheet words for
anchoring restored them.
