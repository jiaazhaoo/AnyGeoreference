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

## Primitive library (v0, drawn from the two kinds already placed)

| primitive | family | from which kind |
|---|---|---|
| colour-plate separation | sheet-reader (deterministic) | historical map |
| OCR of labels and notes | sheet-reader | both |
| printed grid / graticule reading | sheet-reader | historical map (printed coordinates), planning drawing (grid figures) |
| road-name / place-name reading by a VLM | sheet-reader (model) | planning drawing |
| gazetteer search | gazetteer | both |
| address-register lookup | address-register | planning drawing |
| road-network candidate search | road-network | planning drawing |
| control-point fit (affine / similarity / polynomial) | geometry | historical map |
| raster-to-vector match against a base map | basemap | planning drawing |
| snap to map faces, containment, IoU | geometry | planning drawing |
| cross-edition agreement | geometry | historical map |

## The two recipes that exist

| | planning drawing (GB) | historical map (Survey of India, 1 inch) |
|---|---|---|
| cues | road names, house numbers, grid figures, north arrow | printed corner coordinates, graticule, place names |
| references | OS Open Names, address register, road network, OS base map | the printed grid itself, modern vector data, satellite imagery |
| matcher | text-anchor fit; raster-to-vector | control-point fit from printed coordinates, then correction |
| verification | snap to faces, address inside, trace vs polygon | residual at check points (9 m on the pilot sheet), overlay against modern features |
| truth | client's verdict on delivered polygons; hand-drawn boundaries | published georeferencing by the archive; control points |
| abstain when | no snap and no address agreement | residual over the kind's bound; grid unreadable |
