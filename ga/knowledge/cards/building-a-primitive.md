---
id: building-a-primitive
kinds: [any]
cues: []
method: how a missing primitive is built, tested and registered
---
When the plan needs a capability the library lacks, build it; do not abstain for want of a tool that is known to
be buildable. A primitive is one Python function `name(state, **params) -> list` in `ga/primitives/generated/<name>.py`
that reads the loop State (state.cues, state.candidates, state.hypotheses, state.layers, state.sheet.image /
record / meta) and returns new objects of ONE kind: Cue, Candidate, Hypothesis (6 affine coefficients sheet px ->
CRS, a footprint WKT, a score 0..1, a matcher name, a note with the numbers), Layer or Evidence (name, value,
source kind, family). It registers itself at import: `register(Primitive(name, family, deterministic, consumes,
produces, about, impl, "generated", requires=(...)))` with family one of sheet-reader / record-text / gazetteer /
address-register / road-network / basemap / geometry. It must never produce coordinates from a model, only from
data and computation. It ships with a test in `tests/generated/test_<name>.py` that runs on synthetic data in
under a second (no network, no GPU, no real data), and it may reuse the reference data readers already in the
library (OS Open Names sqlite, the Zoomstack road GeoPackage through the pipeline's `roads_near`, the address
register). After the test passes it is imported into the library and the plan that asked for it runs.
