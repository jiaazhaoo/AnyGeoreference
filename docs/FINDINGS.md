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
not bound here, accepts six of the same ten. Per-case rows are kept with the private benchmark.

**The main agent's first plans, 2026-11-06.** Given one to three sheets, a reading of each, six retrieved
knowledge cards and the primitive library, Claude (headless) wrote the plan: recipe, ranked truth sources,
evaluation, stop rules, missing primitives, risks.
- *One drawing with house numbers:* the recipe matched the hand-written one (read, labels, gazetteer with the
  record's address, text anchors with a 3-inlier floor and a 2 mm–2 m scale bound, address inside the footprint,
  the learned matcher as a second hypothesis, matcher agreement); truth = two external authorities (the register for
  the anchors, the record's own address point), explicitly "no batch agreement with one sheet"; tolerance 10 m; a
  risk it raised that the hand-written policy had not: the register is not fully independent of the anchor fit.
- *Three 1943 survey sheets:* pilot on the richest sheet, check on the other two by adjacency; truth ranked
  OSM structure (0.55) above self-consistency (0.5) and batch agreement (0.45); tolerance 500 m; the one-line-off
  frame risk quoted from the knowledge base; and two primitives it asked for: a sheet-index lookup (sheet code ->
  printed bounds; it existed in the source project and is now in the library) and a datum shift from the printed
  survey datum to WGS84 (declared: the real gap behind the 30–650 m offsets we measured against the archive).
- Both plans passed parameters the primitives do not have (`sheets`, `read_for`, `datum_note`); the library now
  drops them at run time and lists them in the plan's problems, so a plan is never refused for a stray parameter.

**Blind test, four inputs the system had never seen, 2026-11-06.** No kind hint; the main agent read each,
retrieved knowledge without a kind filter and wrote a plan; then the executable part of each plan ran.

| input | what the agent read and planned | what ran | outcome |
|---|---|---|---|
| USGS 1:62,500 Boston Bay sheet, 1903 (a survey series from another country) | identified the series, scale and graticule ticks; asked for a datum shift and a "neatline vs next graticule line" safeguard | a generic graticule reader (bounds + interval, no sheet index) found 16 nodes in 1.2 s; poly2 fit, node residual 8.8 m | 23 m rms / 18 m median from the USGS georeference; the printed coordinates themselves sit 18 m from it. Placed, unseen, without a core change |
| 1823 engraved town plan of Sheffield | 19 cues (5 roads, 9 places); plan warned the street pattern has changed since 1823 and asked for a historical-epoch base map | place lookup clustered Castle / Church / High Street into one 3 km area (right); the learned matcher (300 s, GPU) and ORB produced no hypothesis | abstain, as the plan predicted |
| OSM-style render of a suburb | 38 cues (28 roads); plan warned the reference and the sheet are both OSM-derived | place lookup clustered 9 names into a 1.5 km area (right); the learned matcher gave one hypothesis at score 36, rotated 90°, 1,012 m off; ORB none | review, not accepted (score under the bar, no address evidence); overlay agreement read 0.38 at a 1 km miss, so on dense road networks overlay is not a discriminating check |
| oblique photograph of a cathedral | 4 landmark cues, no road, grid or scale; plan asked for an oblique-to-plan rectifier and a landmark lookup | landmark descriptions did not resolve in Open Names; no candidate area | abstain, with the reason recorded |

Four unseen inputs: one placed to 23 m, one held for review at the right area, two abstentions with reasons, no
confident wrong placement. What the test exposed: the overlay check is weak on dense networks; landmark names need
a lookup of their own; an 1823 street pattern needs a reference of its own epoch.

**The two "easy" blind inputs were failing for a reason that was mine, 2026-11-06.** An 1823 town plan and an
OSM-style suburb render both carry dozens of street names in a known city, and the library had no matcher that
uses street names as geometry: the planner could only pick image matchers that cannot read an engraving. Two
primitives fixed it: locate by where the sheet's named roads meet (the pipeline's junction vote), and fit the
labels onto their named road centrelines (rotation x scale x translation swept in one vectorised pass over
distance-transformed road rasters, then point-to-line ICP; no label angles needed). The reader was also told to
list every street name it can read: 19 cues became 75 on the 1823 plan. Result: the 1823 plan placed with 13 of
25 labels on their modern roads (median 59 m, scale 1.4 m/px, rotation 5°), 371 m from the city-centre point; the
suburb render with 17 of 22 (median 32 m, 3.04 m/px), 125 m from the valley's gazetteer point; both accepted by
a new `street_map` kind whose second family is place names found inside the footprint (2 of 7 and 5 of 6).
Lesson: a planner is only as good as the library; when the obvious tool for a kind is missing, add the tool, not
prompt. Replay: `blind/commons/results_street_map.json`.

**Retrieval wants the whole page; matching wants the sheet.** Restricting OCR to the plan crop dropped the
gazetteer's candidate areas from 9 of 10 to 3 of 10; keeping page-wide words for retrieval and on-sheet words for
anchoring restored them.

**The knowledge base, 2026-11-06.** The 13 cards the planner had read so far were our own findings; a planner
reading them could not know that a street-name matcher exists in the trade, so the two easy blind inputs
abstained until I wrote the matcher by hand. The knowledge base is now what a professional georeferencer knows,
written as 75 cards in 13 sections (`docs/KNOWLEDGE.md`): map families and what places each, reading, reference
data, geodesy (projections, datums, meridians, units), transforms, one card per matcher, verification families,
truth and tolerance, failure modes, operation (stopping, cost, abstention reasons, delivery, evaluation design),
building, literature. Capability cards carry `primitives`, `buildable`, `effort`, `ingredients`, and a catalogue
derived from them tells the planner which methods the library implements today and which are known to be
buildable. The four blind inputs were planned again with it, no kind hint, and two of them with the street-name
primitives hidden from the library (`GA_HIDE_PRIMITIVES`) to test whether the main agent now asks for the build:

| input | library | retrieved | plan |
|---|---|---|---|
| 1823 town plan | full | routing, town plans, toponym constellation, marginalia, orientation and scale, insets | street-name route (junction locate, road-name fit), ORB structure as the second matcher, held-out place names inside, overlay margin against shifted poses; tolerance 150 m; risks name the 1736 inset and the compass rose; no missing primitive |
| USGS 1903 sheet | full | routing, survey graticule, small-scale, marginalia, tolerance by scale | graticule bounds, poly fit, residual, **datum shift**, places inside; tolerance 32 m from the 0.5 mm rule; abstain rule names the one-line-off frame; risk: the sheet predates NAD27 |
| oblique photograph | full | routing, oblique photos, photo landmarks, aerial vertical | reads, then one missing primitive `matcher_photo_landmarks` with a four-sentence method (gazetteer lookup, cluster, bearing resection when three landmarks resolve); accept never for a transform; abstain with reason "oblique perspective"; delivers a located Candidate |
| suburb render | street-name primitives **hidden** | routing, road networks, street names as geometry, text anchors, town plans | names all three hidden primitives as missing with implementable methods (name normalisation and token ratio, junction votes within 150 m, distance-transform rasters per road, 5 degree x log-scale sweep, ICP on inliers, held-out places weighted by rarity) and puts them in the recipe at their steps; ORB structure agreement as the second family |
| 1823 town plan | street-name primitives **hidden** | as above | the same three primitives named as missing, methods written from the card (junction votes over the OSM network seeded by the place cluster, RANSAC similarity over label-centreline pairs with a scale bound, held-out names inside the footprint), placed in the recipe between the place lookup and the structure check |

Before the knowledge base, the same agent on the 1823 plan chose the learned image matcher and asked for a
"historical-epoch base-map renderer". The difference is not the model: it is that the method is now written down
with its ingredients, and the catalogue says the library lacks it and that it is buildable. Plans still pass
parameters outside the primitives' contracts (dropped and listed); contract granularity remains the open item.
Replays: `blind/plans_kb2/*.json` (data folder).

**Blind test 2: the whole flow on four unseen public maps, 2026-11-06/07.** Read, plan (knowledge base), build what
the plan names, execute, decide (generic two-family policy), revise up to twice on the results. Inputs from Wikimedia
Commons, record "a scanned map, place and kind unknown": a 1900 Admiralty chart of the Thames, an Ordnance Survey
surveyor's drawing round Norwich (hand-drawn, c. 1817), the two page halves of an 1884 engraved Norwich street plan,
an 1806 Leeds town plan (coarse halftone).

| batch | outcome | why |
|---|---|---|
| Norwich 1884, two halves | **both accepted** | road-name fit 23/36 and 17/22 labels on their roads (median 48 m, 21 m); Tombland inside the left half, the railway station by the right; second family = batch agreement: the right half's origin falls at +0.93 sheet widths, 0.00 heights in the left half's frame (they meet edge to edge, 7% binding overlap); scale and rotation equal (both fits sit on the same sweep cell, so that part is weak; the seam is the real check) |
| Thames chart 1900 | abstain (3 runs, 2 revisions each) | the first reading had the printed lat/long border, later readings (cache cleared) did not, so the graticule route was never tried; the built toponym matcher found 2-3 consistent triples inside a 3 km candidate (the chart spans 12 km); OSM by Overpass timed out and the planner pointed the local renderer at a wrong layer. Placeable from names: a non-mirrored similarity over the 9 names unique in the area gives 6/9 inliers, median 241 m, 2.94 m/px |
| OS drawing c. 1817 | **wrong accept** (revision 1) | the built toponym matcher placed it mirrored (top of the sheet to the south), 5/45 name inliers, rms 298 m, 37 x 35 km footprint; median error of 52 village labels 15 km; accepted because "2 places inside the footprint" counted as a second family although the matcher itself used place names, and a 1,300 km2 footprint holds two of anything. The sheet is placeable: a plain non-mirrored similarity by RANSAC over the 51 names unique in the area gives 35/51 inliers, median 580 m, 9.85 m/px, north up |
| Leeds 1806 | abstain | 12 cues; the scan is too coarse to read street names |

One wrong accept (the 1817 drawing, above), reported first as an abstention because a truncated status line was
misread. Two rules it broke that the knowledge base states and the code did not enforce: never allow a reflection
unless the text test found one (failure-rotation-and-mirror), and a check that consumed the same cues as the fit is
not a second family; "inside" must not be trivial for the footprint's size (verify-evidence-families,
verify-address-in-footprint). The builder wrote four primitives on its own across the passes (toponym constellation, polyline
shape, thin plate spline, neighbour-sheet tiling), each with a passing synthetic test. The test found seven framework
faults, all fixed: reader turn limit; cut-off plan JSON (retry shorter); planner blind to param contracts; a missing
required param crashed the run; a raising tool ended the sheet; a revise answer in another JSON shape was lost; road
primitives defaulted to one town. And three that cost a night: one tool spun for seven hours (now a 300 s deadline
per tool, and the watcher reports stalls); planner params of the wrong type or guessed data paths broke steps that
worked at their defaults (now cast or dropped, defaults preferred); the generated tiling check could never run
because the executor ran sheets one by one (batch agreement now runs at batch level). Lesson: the planner's own
parameter tuning made a placeable sheet fail; defaults tuned on real sheets beat guessed values.

**Public demo: USGS historical quadrangles, a graticule reader written for it, 2026-11-08.** The bound graticule
reader lives in a private repository, so a generic one was written from scratch (`ga/primitives/graticule.py`,
OpenCV and numpy only). Thin dark lines are found by a ridge test across the line (darker than both pixels 3 px
away), so water tint and type do not compete with a hairline. Strip profiles with a small skew search give
candidate lines with a strength (the share of the span where the line is present). Every evenly spaced family of
n+1 lines is enumerated per axis, and a meridian family and a parallel family are paired only when their spacing
ratio is cos(latitude) (paper or a projected raster) or 1 (a raster in degrees), within 3 %. Each kept line is
refined strip by strip, with its own slope, because meridians converge. On Boston Bay the 16 nodes come out in
0.4 s. Median node distance from the USGS georeference is 9–10 m, and the worst node is about 50 m, at the west
neatline: the printed line sits about 10 px from where USGS's own georeference puts −71°, while the east edge
matches to a pixel. Part of every "error" below is the archive's.

The second family was first feature matching (SIFT + RANSAC) between the two scans. Two printings of the 1903
edition share 1,588 inliers, but the 1892 and 1903 editions share 9. The 1903 edition was re-drawn: its lettering,
wave lines and hachures are new. Replaced by resampling both scans onto one lon/lat grid through their own
placements, masking the graticule bands (they agree by construction) and phase-correlating the rest. Results: a
re-drawn edition pair shifts 31 m, two printings shift 1 m, and a simulated misread one meridian off shifts 6,863 m
(5′ of longitude there is 6,853 m).

Ten cases, 20 scans (`demo/cases.json`). On the 14 scans of seven real sheets: 12 accepted, all right (median
6–19 m, worst grid point 24–38 m from USGS). Two went to review: Duluth 1953, where the Public Land Survey section
grid was read as the graticule (residual 9.7 m, placement 26 km off, the content check found no correlation), and
its 1895 partner, which was right but had nobody to agree with. Controls: two 1:24,000 sheets (ticks, no lines)
abstain; a pair of two different sheets goes to review (no overlap). A record with the bounds one interval off is
accepted 6.9 km off on both scans: the evidence cannot see a wrong record. That is the next family to build
(reading the printed corner coordinates). The 1:24,000 abstention is honest, not a capability: a tick-and-cross
reader would place them.

**Held-out: 100 USGS 15' quadrangles drawn at random, run once, 2026-11-08.** The demo's sheets were hand-picked, and
its thresholds were set by looking at Boston Bay, so its numbers are development numbers. Held-out protocol: a sampler
that never opens an image (`benchmarks/sample_usgs15.py`; seeded uniform points over the contiguous US, the 15'
1:62,500 quadrangle holding each point, two scans by a fixed draw, the development quadrangles excluded). The draw
is 100 quadrangles, 31 states, editions 1893–1970, mostly from the 1940s and 1950s, and it reproduces byte for byte.
The decision code was frozen at commit 72f30da (decision-code sha256 b97ec9ae7899, identical to the published demo),
and the run was made once (690 s, no errors). Nothing below was tuned afterwards.

200 scans: 55 accepted, **0 accepted wrong** (worst grid point of any accepted scan 42 m from USGS, median of worsts
31 m); 40 to review (15 with a right placement, 25 with a wrong one); 105 abstained. By era: before 1930, 31 of
44 accepted and nothing wrong reached review; 1930–1944, 21 of 41; from 1945 on, 3 of 115. Failure classes, each a
capability, not a case:

1. **No graticule lines (abstain, 88 of the 105 from 1945 on).** Later 15' sheets print the graticule as edge ticks and
   interior crosses. The reader looks for lines only. Capability: a tick-and-cross reader (the same need as the
   1:24,000 control).
2. **Another grid taken for the graticule (25 wrong placements, all held back).** The Public Land Survey sections, as in
   Duluth 1953, and other ruled grids. 20 of the 25 were read under the "raster in degrees" hypothesis (spacing ratio
   1, which square sections satisfy), with the weakest line present on only 20–32 % of its span. The residual is no
   help: 8–61 m at the nodes for placements 3–32 km off. The reader accepts too weak a family and has no reason to
   prefer paper over degrees. Capability: the graticule must be the family that meets the neatline and carries the
   ticks, and the pixel space must be decided once per sheet from evidence, not tried until a family fits.
3. **The near miss: shared misreads agree.** In q048 and q096 both scans were read the same wrong way (same plate,
   same section lines) and the content check said they agree (shift 0). They were kept from acceptance only
   because a rival family scored at least 85 % of the chosen one (`graticule_ambiguous`), plus a residual over the
   bound on one scan. The second family is not independent of a systematic reading error shared by both scans, and
   the record typo control showed the same thing. Capability: a family that does not come from the sheet's own lines,
   for example the map content against an external base map (coast, rivers, roads), or the printed corner
   coordinates read as text.
4. **Right placement, nobody to agree with (15 to review).** The partner scan abstained or was misread, so there was
   nothing to compare. This resolves when classes 1 and 2 do.

The development numbers (12 of 14 accepted) were optimistic about coverage (55 of 200 held-out) but not about
safety: neither set had a wrong acceptance outside the deliberate record-typo control. Results:
`benchmarks/results/usgs15_heldout_v1.md` and `.json`. A next change is measured on a fresh draw (a new seed),
because this one has now been looked at.

**The frame-and-marks reader, and held-out v2, 2026-11-08.** Built for failure classes 1 and 2 of v1 (no lines;
another grid taken for the graticule) as one reader, `graticule_marks`, developed only on the demo set and the
already-seen v1. The neatline is the rectangle of long lines that has the shape of the record's bounds and where
the map content stops on every side, judged by its weakest side. Every graticule node is then predicted from the
four corners and confirmed by a mark: a one-sided tick on the edge or a cross inside. A ruled grid runs on both
sides of the neatline; a tick does not. With fewer than half the marks there are no cues.

Three general findings came out of development, all from looking at failures by class:
- One global skew per axis lost one side neatline on polyconic sheets, because meridians converge and the two sides
  lean opposite ways. Every line now gets its own slope from a slope × position accumulator: 147 → 191 of 216
  development scans with the right frame.
- Allowing "pixels in degrees" let square section grids pass for a graticule. A scan of paper has metric pixels,
  and only the record can say a raster is in degrees.
- "The outermost frame with marks" fails: a collar line just outside the neatline takes the corner labels for marks.
  It was tried and dropped (16 of 216).

Development result on v1 (not a measurement): 55 → 146 of 200 accepted, 0 wrong.

Held-out v2: a fresh draw (seed 20261109, 100 quadrangles, editions 1889–1978, none seen before), committed with
the frozen code before it was run, and run once (926 s, no errors). Results: 129 of 200 accepted, **0 wrong** (worst
grid point of an accepted scan 62 m); 63 to review (39 right, 24 wrong); 8 abstained. By era: before 1930, 36 of 49
accepted; 1930–1944, 24 of 43; from 1945 on, 69 of 108 (v1 with the lines reader: 3 of 115). The 24 wrong placements
were all held back: 21 had no content correlation with the other edition, and 3 had no partner placed. None was a
shared misread that agreed.

What it costs, and what it does not fix:
- **Over-caution.** 17 right placements whose editions agree were held by the ambiguity rule, which fires when a
  rival frame scores within 85 % even if the rival lies a few pixels from the chosen one (a double neatline, a road
  along the edge). The rule should ask whether the rival places the sheet elsewhere. Next capability; measured on
  a fresh draw.
- **Precision on line graticules.** Mark positions are coarser than whole-line fits. On the demo's line sheets the
  node residual rose from 5–11 m to 6–30 m, and one scan (Ithaca 1895) went over the 30 m bound to review.
  Refining a confirmed mark along its full line where one exists would recover it.
- **The record typo is still accepted** (6.9 km off). This reader does not address it; an external family is
  needed.
