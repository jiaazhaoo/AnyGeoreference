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

**Claude as the reader, the composer and the planner (simulated in conversation, 2026-11-06).** The platform's
own model does the three model jobs; today it did them by hand, with every choice and reason recorded.
- *Reader:* ten drawings read, cues with pixel boxes written to files the loop consumes. On the sheet with house
  numbers along a road, Claude's eight numbers raised the text-anchor fit from 3 of 4 inliers (OCR) to 11 of 12,
  placement 7 m from the graded polygon. On a floor plan and a setting-out plan it read correctly that nothing on
  the sheet places it.
- *Composer:* asked to compose each kind's recipe from the 23-primitive library given the profile, Claude's
  compositions matched the human specs at Jaccard 0.83 (drawings: it added its own reader, left out the overlay
  check), 1.0 (historical sheets) and 0.71 (unlabelled raster: it added a reader and an agreement check that cannot
  fire); step order agreed 1.0 on every kind; no invented primitive.
- *Planner:* three drawings driven one tool at a time from the state summary (no coordinates). Numbers-along-a-road:
  10 steps, a verified placement at 7 m, sent to review because the overlay check stayed at 0.2 (the accept rule
  wants 0.3). Floor plan: 1 step, abstain. Sketch with one road name and no numbers: 7 steps, every matcher tried,
  abstain. The fixed plan runs 11 steps on all three regardless.

**Planner (Claude, headless) vs the fixed plan on ten drawings, 2026-11-06.** Same tools, same cache, same truth;
the planner saw only state summaries without coordinates (88 calls, claude-sonnet-5 through the subscription CLI
in an isolated config). Outcomes were identical case for case: one verified placement at 7 m sent to review, nine
abstentions; no discordant pair (McNemar p = 1.0). What differed was the path: the planner never reproduced the
fixed sequence, took 4 to 12 steps (mean 7.9) against the fixed 11, stopped after 4 on the floor plan and the
setting-out plan with the right reason ("nothing on this sheet places it"), and wasted steps where the tool
contracts were too coarse: it called the structure matcher before any sheet-side structure existed because the
registry declares the matcher's input only as "layer", not "a sheet structure layer and a reference render". Two
lessons: on this sample the planner adds judgement about when to stop, not placements; and a planner is only as
good as the input/output types the tools declare. Replay: `experiments/planner_vs_fixed_plans10/report.json`.

**The pipeline's learned matcher, bound and run on CPU (degraded), 2026-11-06.** MINIMA sliding-window matching
against OS tiles was bound as `plan_minima_match` (seed = the candidate area, rotation from a read north arrow,
scale from a read scale). With the GPU held by a production job it ran on CPU with 40 windows and no road-name
seed: 6 of 10 cases in the hour before the run timed out, 5 to 23 minutes a case. It produced hypotheses on three
(scores 16–20 against the pipeline's acceptance bar of 50): 148 m and 291 m from the truth, address outside, so the
policy keeps them for review; on the numbered sheet the text-anchor fit (7 m) stayed best. This says the binding
works, not what the matcher can do: the production run of the same ten cases, on GPU with its road-name seeding,
accepts six. A GPU rerun with production parameters is queued for when the GPU is free.

**The learned matcher on GPU, ten drawings, 2026-11-06.** Production window count (100), 300 s a case, seeded by
the gazetteer candidate, rotation from the read north arrow, scale from the read scale. Hypotheses on 9 of 10;
within 100 m of the graded polygon on 5 (7, 13, 86, 90, 99 m), within 500 m on 7. The matcher's own score is not
a safe gate: at the pipeline's bar of 50 it accepts four, one of them 736 m off; with the address point inside the
footprint as a second family it accepts two, both right (13 m, 86 m), and with the text-anchor fit (11 of 12
inliers, address inside) a third at 7 m. It also "placed" the floor plan 998 m away at score 26, a sheet the
reader had already flagged as carrying nothing that places it: the policy now abstains when no location cue was
read. Rules fitted on these ten are marked provisional in `ga/kinds.py`; the production flow, with road-name checks
not bound here, accepts six of the same ten. Per-case rows: `per-case rows kept with the private benchmark`.

**Retrieval wants the whole page; matching wants the sheet.** Restricting OCR to the plan crop dropped the
gazetteer's candidate areas from 9 of 10 to 3 of 10; keeping page-wide words for retrieval and on-sheet words for
anchoring restored them.
