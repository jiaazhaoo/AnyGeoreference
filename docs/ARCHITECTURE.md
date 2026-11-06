# Architecture

Three levels. L1, the runtime loop per sheet, is this file. L2, recipes per kind of map (profile, compose, generate, pilot, freeze), is `RECIPE.md`. L3, production per batch (budget, caps, sentinel, rollback), is delegated to a control layer such as ReinsLite.

## 1. Objects (`ga/model.py`)

| object | fields | rule |
|---|---|---|
| `Sheet` | id, kind, image ref, digest, record (free text the input came with), meta | the unit of work; `kind` picks the adapter |
| `Cue` | text / symbol, kind (road, number, place, arrow, scale, landmark), bbox on the sheet, reader, confidence | produced only by SEE; never a coordinate |
| `Candidate` | area (polygon in target CRS), source (gazetteer / address / road / basemap), the cues it answers, score | produced only by RETRIEVE |
| `Hypothesis` | transform (sheet pixels -> CRS), site polygon in CRS, score, matcher, candidates used | produced only by MATCH; always a list, best first |
| `Evidence` | name, value, source kind, family, cost (from `evalcore.Evidence`) | produced by VERIFY and by any step that wants to be counted |
| `Verdict` | placement (a Hypothesis) or `abstain`, probability, evidence set, trail, cost | produced only by DECIDE |

Invariants, enforced in code: a `Cue` has no coordinates; a `Hypothesis` has no reader; a `Verdict` without a
calibrated probability is invalid; every object carries the digest of the sheet it belongs to.

## 2. Tools (`ga/tools/registry.py`)

A tool is a declared callable: name, inputs (which object kinds it consumes), output kind, independence family,
deterministic or not, cost model, implementation. The registry is what both drivers see. Declaring the family at
registration is what lets DECIDE count corroboration honestly: two readers of the same sheet are one family.

| family | examples |
|---|---|
| sheet-reader | a VLM reading road names; OCR |
| record-text | the application's own address / description |
| gazetteer | place-name search |
| address-register | address point lookup |
| road-network | street geometry search |
| basemap | raster / vector base map matching |
| geometry | snap to faces, containment, IoU |

## 3. Drivers (`ga/loop.py`)

- `FixedPlan`: an ordered list of tool names; the production baseline, fully reproducible.
- `Planner`: an LLM is shown the registry (names, what each consumes and produces, cost) and the current state
  (which objects exist, their scores) and picks the next tool, or `stop`. Bounded by a step cap and a cost cap.
  The planner never sees coordinates it could copy; it sees object summaries.

Both drivers write the same trace: one line per tool call with inputs, outputs, cost, seconds. The comparison
"planner vs fixed plan, same tools, same cache, same benchmark" is the first experiment.

## 4. Decision (`ga/decide.py`)

Thin: builds the `EvidenceSet`, runs a `geo-eval` `Policy` (rules such as "best hypothesis snaps to map faces at
IoU >= t and the address point lies inside" -> accept), converts the score to a probability with a `Calibrator`
fitted on the benchmark's dev split, and abstains when no accept rule fired or the probability is under the kind's
threshold. The policy is measured on the benchmark; its table is the explanation.

## 5. Kinds (`ga/kinds.py`)

A kind binds a recipe to: how to load the sheet, which tools exist for it (implementations), the policy, the
calibrator. v0: `plans_gb` (planning drawings, Great Britain), implemented by wrapping the production pipeline's
georeferencing functions (grid-figure reading, road-name fits, gazetteer seeding, raster matching, snapping).
Next: `microfilm`, `historical_map` (open data: OSM / archive scans).

## 5b. Knowledge (`ga/knowledge/`)

The planner and the builder read a curated knowledge base before acting (`KNOWLEDGE.md`): 75 cards in 13 sections,
retrieved by TF-IDF with kind and cue filters, plus a capability catalogue derived from the cards that states for
every known method which library primitives implement it and whether a missing one is buildable. The rule the
cards and the planner prompt share: a method the knowledge names and the library lacks is built (one function,
one output kind, a synthetic test, a worktree, a review branch), not abstained on; a method the knowledge marks
not buildable is a typed abstention.

## 6. Benchmark (`benchmark/`)

Layered by kind; truth = a polygon whose location is confirmed externally (a client's pass on a delivered polygon,
or a hand-drawn boundary), tolerance per kind. Built and gated with `geo-eval`'s `Benchmark` and `Gate`. The first
set: 100 drawings the fixed plan could not place but whose truth is known: the failing slice. The number that
matters there is *placed wrong*.

## 7. What this is not

- Not a general vision model. No training of a "georeference anything" network; generality is in the interfaces.
- Not a rule pile. Reading is the model's job; rules decide, they do not read.
- Not an answer machine. Every output is a set of hypotheses and a probability, or an abstention.
