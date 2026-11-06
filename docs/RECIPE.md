# Level 2: recipes — how a *kind* of map gets georeferenced

The runtime loop (ARCHITECTURE.md) answers "where does this sheet go". A recipe answers "how do sheets of this
kind get placed at all". A user brings any map; the framework profiles it, finds or composes a recipe, generates
the adapter from it, proves it on a pilot with truth, and freezes it. Only a frozen recipe reaches production.

## Objects (`ga/recipe.py`)

| object | holds |
|---|---|
| `Profile` | what the sample sheets are: colour plates, text kinds and scripts, printed grid / graticule, scale, projection hints, symbols, era, language; measured on the samples, not guessed |
| `Recipe` | the plan: which cue kinds to read and with what reader; which reference sources to query; which matchers; which verifications; the policy rules; expected accuracy band; expected cost per sheet; the recipe it was derived from |
| `AdapterSpec` | the generated adapter as data: an ordered composition of primitives with parameters, plus the policy table; the code is rendered from this and nothing else |
| `Pilot` | sample sheets with truth (control points, known locations, or cross-version agreement), the run's metrics, the gate result |
| `RecipeVersion` | Recipe + AdapterSpec + Pilot + digests, frozen |

## Workflow

```
Profile   measure the samples            -> Profile
Match     nearest known recipes          -> candidates to reuse with parameter changes
Compose   if none fits: an agent composes from the primitive library   -> Recipe
Generate  render AdapterSpec -> code (composition + parameters only)   -> adapter module
Pilot     run on samples with truth; geo-eval benchmark + gate         -> Pilot
Gate      placed-wrong, abstained, calibration, cost within the kind's bounds
Freeze    RecipeVersion; else revise Recipe and pilot again
```

## Two rules that keep this from being "an LLM writes code"

1. **Composition only.** Generated code may call primitives and set their parameters. A primitive is deterministic,
   tested, and declares its inputs, output kind and independence family. A new primitive is written by a person,
   reviewed, tested, then added to the library. The agent chooses; it does not invent.
2. **No truth, no recipe.** A pilot needs external truth: a few control points from the user, known locations from
   a gazetteer or register, or agreement across editions of the same sheet. A recipe without a passed pilot is
   marked unverified and cannot be frozen.

## Primitive library (v0, generated from `ga/primitives`)

| primitive | family | deterministic | consumes → produces | source | implemented |
|---|---|---|---|---|---|
| control_point_fit | geometry | yes | cue → hypothesis | generic | yes |
| residual_check | geometry | yes | hypothesis, cue → evidence | generic | yes |
| hypothesis_agreement | geometry | yes | hypothesis → evidence | generic | yes |
| ocr_cached | sheet-reader | yes | – → cue | plans_gb | yes |
| ocr_words | sheet-reader | yes | – → cue | plans_gb | yes |
| road_and_place_labels | sheet-reader | yes | cue → cue | plans_gb | yes |
| vlm_read_names | sheet-reader | no | – → cue | plans_gb | declared |
| gazetteer_search | gazetteer | yes | cue → candidate | plans_gb | yes |
| grid_figures | geometry | yes | cue → hypothesis | plans_gb | yes |
| text_anchor_fit | geometry | yes | cue → hypothesis | plans_gb | yes |
| address_in_footprint | address-register | yes | hypothesis → evidence | plans_gb | yes |
| snap_faces | geometry | yes | hypothesis → evidence | plans_gb | declared |
| graticule_frame | sheet-reader | yes | – → cue | soi | yes |
| plate_separation | sheet-reader | yes | – → layer | soi | yes |
| line_structure | sheet-reader | yes | layer → layer | soi | yes |
| osm_reference | basemap | yes | candidate → layer | soi | yes |
| structure_match | basemap | yes | layer → hypothesis | soi | yes |
| cross_edition_agreement | geometry | yes | hypothesis → evidence | soi | yes |
| edge_structure | sheet-reader | yes | – → layer | raster | yes |
| hint_area | record-text | yes | – → candidate | raster | yes |
| reference_render | basemap | yes | candidate → layer | raster | yes |
| structure_match_orb | basemap | yes | layer → hypothesis | raster | yes |
| overlay_agreement | basemap | yes | hypothesis, layer → evidence | raster | yes |

"declared" = in the library with its contract but no implementation on this machine (needs the bound repository, weights or a key); a recipe may still name it, and `kinds.unavailable()` says so before any run.

## The three kinds that exist (`ga/kinds.py`)

| | planning drawing (GB) | historical map (Survey of India, 1 inch) | unlabelled raster (aerial / satellite / map extract) |
|---|---|---|---|
| cues | road names, house numbers, grid figures, north arrow | printed corner coordinates, graticule, place names | edges only; no text |
| references | OS Open Names, address register, road network, OS base map | the printed grid itself, modern vector data, satellite imagery | a hint area from the record or the user; reference vectors rendered over it |
| matcher | text-anchor fit; raster-to-vector | control-point fit from printed coordinates, then correction | structure match (linework / edges vs rendered reference) |
| verification | snap to faces, address inside, trace vs polygon | residual at check points (9 m on the pilot sheet), overlay against modern features | overlay agreement; agreement between matchers |
| truth | client's verdict on delivered polygons; hand-drawn boundaries | published georeferencing by the archive; control points | known tile footprints; control points |
| abstain when | no snap and no address agreement | residual over the kind's bound; grid unreadable | no candidate area, or overlay under the bound |
