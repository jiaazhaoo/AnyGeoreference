# Georeference Anything

**Put any scanned drawing or map on the Earth, say how sure you are, and say no when you are not.**

Status: v0 design and core loop (2026-11). Kinds placed so far: scanned planning drawings (Great Britain) and historical 1-inch survey sheets (South Asia). A new kind is a recipe, not a rewrite; the core does not change.

## Why

Georeferencing a scanned plan is a multi-step task that needs both reading and computing: somebody has to read the
road names, house numbers and place names on the sheet, then find where on the national map those names fit, then
check the fit. Language and vision models read well and compute badly; they are not deterministic and cannot be
trusted with coordinates. Spatial tools compute exactly and read nothing. A system that lets the model read and the
tools compute, keeps every hypothesis with its score, verifies against evidence the model did not produce, and
abstains when the evidence is thin, is more defensible than either alone. That principle is stated in the literature
on language-guided spatial analysis; this repository is one end-to-end instance of it with a benchmark that has
external truth.

The name is a direction, not a claim: generality comes from the tool and knowledge interfaces, not from one model.

## Three levels

| level | question | answered by |
|---|---|---|
| L1 runtime, per sheet | where does this sheet go | the loop below |
| L2 recipe, per kind of map | how do sheets of this kind get placed at all | profile the samples, compose from a primitive library, generate the adapter, pilot with truth, freeze (`docs/RECIPE.md`) |
| L3 production, per batch | how to place thousands without an accident | a control layer: budget, caps, sentinel, rollback |

Two kinds are placed today: planning drawings (Great Britain) and 1-inch historical survey sheets (South Asia). A user who brings a third kind goes through L2.

## The loop

| step | who | produces |
|---|---|---|
| SEE | a vision-language model | cues: text and symbols read off the sheet, with where on the sheet they are |
| RETRIEVE | gazetteers, address registers, road networks, base maps | candidate areas that could hold those cues |
| MATCH | deterministic matching (text anchors, raster-to-vector, raster-to-raster) | placement hypotheses: a transform, the site polygon in the target CRS, a score; always a set |
| VERIFY | independent checks (snap to map faces, address point inside, drawing relations vs map relations) | evidence with an independence family |
| DECIDE | a measured policy and a calibrator (from `geo-eval`) | a placement with a probability, or *abstain*; the trail; the cost |

The same tools run under two drivers: a fixed plan (the production baseline) and an LLM planner that chooses the
next tool from the registry. Both are evaluated on the same benchmark, which is the experiment this repository exists
to run: what does a model's reading add to deterministic georeferencing, and when must it abstain.

## What we measure

Per kind of input, on cases whose true location is known from an external source: placed right, placed wrong
(weighted heavier than an abstention), abstained, cost, and calibration (`ga/bench.py`, through geo-eval).

First numbers (2026-11-06, data stays out of the repository):

| kind | input | truth | result |
|---|---|---|---|
| historical map | one Survey of India quarter sheet (1943), the archive's published raster taken as pixels only | the archive's own georeference | 49 graticule nodes read in 2.7 s; our placement 33 m rms / 29 m median from the archive's; the sheet's printed coordinates themselves sit 31 m from the archive's, so the loop reproduces the printed placement and the rest is the archive's datum shift |
| unlabelled raster | a road-network render of a city district, rotated 7° and shifted, with a location hint 0.5 km off and no text | the known transform | ORB + RANSAC against reference roads: corners 5–7 m, centre 1 m, overlay agreement 0.85, in 0.5 s |
| planning drawing | ten frozen benchmark drawings with cached OCR, OS Open Names and the local address register | the client's graded polygon | the gazetteer finds a candidate area for 9 of 10; text anchors (house numbers × road names against the register) place 1 of 10, 8 m from the truth with the address inside; the generic ORB matcher places 0 of 10; the production pipeline's learned matcher, not yet bound here, accepts 6 of the same 10 |
| historical map, five sheets | five sheets from two series and three decades, pixels only | the archive's georeference, 100 m at the centre | see `docs/FINDINGS.md`: two sheets read one graticule line off (9 km) with a 40 m node residual; the first policy accepted them; the policy now needs a second evidence family and sends them to review |

## Run it

```bash
python -m ga.cli kinds                      # the three kinds, their steps, what is unavailable on this machine
python -m ga.cli primitives                 # the library: family, determinism, contract, source, implemented?
python -m ga.cli run --kind soi_1inch --image sheet.tif --record '{"sheet_code": "053BSW"}'
python -m ga.cli run --kind unlabelled_raster --image tile.png --record '{"hint_xy": [435000, 387000]}'
python -m ga.cli run --kind plans_gb --image page.jpg --record '{"address": "..."}' --meta '{"ocr_jsonl": "...", "page": "..."}' --planner
python -m pytest -q tests
```

Bound primitives need their source repositories and data (the planning pipeline with OS Open Names, AddressBase
and Zoomstack; the historical-map project with its MINIMA weights; Overpass). Everything else runs anywhere.

## Where it sits

- `geo-eval`: the policy table, calibration and the gate that every change must pass
- the production pipeline this grew out of supplies the first adapter's tool implementations

## Origin

Grown from a production system that places planning drawings on the national grid for a client
(2026-09 to 2026-11); its measured dead ends (rotation sweeps, longer search budgets, confirmation scores) are what
this design answers. Data and client names stay private.
