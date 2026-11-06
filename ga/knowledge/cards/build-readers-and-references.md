---
id: build-readers-and-references
kinds: [any]
cues: [text, place, road]
method: a new reader (a text spotter, a symbol detector) or a new reference (a gazetteer, a layer) is also a primitive to build
tags: [new reader, text spotter, symbol detector, new reference, gazetteer import, layer import, binding, adapter]
see: [build-a-primitive, reading-text-spotting, reference-gazetteers, reference-basemaps-and-rasters]
---
Capabilities are not only matchers. A reader is a primitive that produces Cues: binding a map-text spotter, a
north-arrow detector, a symbol detector (churches, stations, trig points), a colour-plate separator (water in
blue, contours in brown) or a neatline finder is a reader build, with the same contract (pixel boxes and text,
never coordinates) and a synthetic test (a rendered image with known boxes). A reference is a primitive that
produces Candidates or Layers from a data source: importing a historical gazetteer, a national names set, a
footprint layer, an archive's tile service for a series, with the request cached by hash and the licence
recorded. The library's floor for a new region or era is three primitives: a reader for its text, a gazetteer for
its names, a layer for its structure; with those, the generic matchers and verifications run unchanged. A plan for
a new country lists exactly which of the three are missing; a plan for a new era lists the historical gazetteer
and the georeferenced edition it would use. Model weights for readers are versioned and registered like data, not
committed to code.
