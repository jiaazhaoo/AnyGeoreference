# The knowledge base: what a professional georeferencer knows, as cards the planner reads

`ga/knowledge/cards/*.md`, 75 cards, about 15,000 words, in 13 sections. The main agent retrieves from it before it
writes a plan; the builder retrieves from it before it writes a primitive; a person reads it as the handbook. The
cards are curated prose, not generated: a method per card, the numbers we measured, the faults we have seen, the
literature's conclusions, and for every method the honest statement of whether the library implements it today and
whether a missing implementation is known to be buildable.

## Sections

| section | cards | what they hold |
|---|---|---|
| `routing-*` | 3 | the first question (what ties this sheet to the Earth), the funnel from the world to the metre, the batch contract (1–3 similar sheets, pilot/check) |
| `family-*` | 14 | map families and what places each: survey graticule sheets, grid and series sheets, town plans, cadastral/tithe/estate, planning drawings, nautical charts, small-scale thematic, vertical aerial, oblique photographs, satellite/drone, sketch/schematic, atlas pages and insets, structure-only rasters, British historic series |
| `reading-*` | 6 | the reading contract (pixel boxes, never coordinates), marginalia, map text spotting, orientation and scale from the sheet, the site marking, the hallucination guard |
| `reference-*` | 7 | which reference for which cue; gazetteers (modern and historical), road networks and name normalisation, address registers, base maps and georeferenced rasters, the epoch problem (what persists), licensing and privacy |
| `geodesy-*` | 4 | identifying the projection from the graticule, datums and the size of their shifts, prime meridians and units, CRS and output formats (GCPs, world files, IIIF Georeference Annotation) |
| `transforms-*` | 3 | model choice and minimum control points, residual pattern diagnostics, paper and scan distortion |
| `matcher-*` | 13 | one card per method: graticule corners, grid labels, sheet index, text anchors, street names as geometry, toponym constellation, polyline shape, learned image matching, render-and-correlate, building footprints, parcel boundaries, map-to-map editions, photo landmarks |
| `verify-*` | 7 | evidence families, the catalogue of checks and how each fools you, dense-network overlay, neighbour sheets, address inside, places inside, the acceptance policy with calibration and gate |
| `truth-*` | 3 | ranking truth sources, tolerance by scale (0.5 mm rule, CE90/95), auditing truth itself |
| `failure-*` | 3 | the symptom → cause → check catalogue, the one-line-off lattice, rotation and mirror |
| `operate-*` | 5 | stopping, cost and time, typed abstention reasons, delivery contents, evaluation design and the improvement loop |
| `build-*` | 3 | the primitive contract, capability determination (what is buildable here, what is not), readers and references as primitives |
| `literature-*` | 4 | historical-map georeferencing, image matching, language models for GIS, accuracy standards |

## Card format

```
---
id: matcher-toponym-constellation          # = file name; section = first word
kinds: [historical_map, street_map]       # recipe families, or [any]
cues: [place, landmark]                   # cue kinds the card speaks to (boost at retrieval)
method: one line, what the method is
tags: [free words that help retrieval]
see: [related card ids]                   # checked by the tests
primitives: [library names]               # capability cards: what implements it today
buildable: yes | no                       # capability cards: known to be buildable here?
effort: hours / half a day / one day …    # and what the build consists of
ingredients: data and libraries the build needs
---
prose, 100–300 words, numbers where we have them
```

## Retrieval (`ga/knowledge/__init__.py`)

TF-IDF over text + method + tags + id, stopwords removed, with a kind filter (a card for `planning_drawing` is not
shown for a historical map; `[any]` cards always qualify) and a 1.5× boost when the card's cue kinds meet the
batch's. Deliberately simple and replaceable: an embedding index can take the same `retrieve(query, kind, cues,
k)` interface. `python -m ga.cli knowledge "coastline shape no text" -k 5` shows what a query returns;
`python -m ga.cli knowledge` lists the sections; `--catalogue` prints the capability catalogue.

## The capability catalogue: how a missing method becomes a build, not an abstention

`Index.catalogue(library, hidden)` derives one line per capability card: the method, the library primitives that
implement it (`in library: …`), the ones missing (`NOT in library`), and `buildable: yes, effort …, needs …` from
the card. The planner reads it under the retrieved cards (`ga/orchestrate.py: knowledge_for`), and its system
prompt says: a method the knowledge names and the library lacks goes into `missing_primitives` with a concrete
`method` and into the recipe at its step; the builder (`ga/builder.py`) then retrieves the capability card for
that primitive and writes it. This is the answer to the two "easy" blind inputs that failed before the street-name
matcher existed: the knowledge of the method was in the literature all along; the system lacked the determination
to build it. Determination = the rule in `build-capability-determination` + the catalogue + the builder.

Cards with `buildable: no` (oblique photographs: camera pose from one image) tell the planner to abstain with the
typed reason instead of forcing a fit.

## Adding knowledge

A new finding (a measured failure, a number, a method that worked) goes into the card it belongs to, dated; a new
method gets a `matcher-*` card with `primitives`, `buildable`, `effort`, `ingredients`; a new map family gets a
`family-*` card that names its methods. `tests/test_knowledge.py` checks that every card is well formed, every
`see` link resolves, every named primitive exists in the library, and that the classic queries still route to the
right cards. No client names, no addresses, no licensed extracts in any card.
