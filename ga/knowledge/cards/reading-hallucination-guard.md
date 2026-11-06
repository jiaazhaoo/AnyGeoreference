---
id: reading-hallucination-guard
kinds: [any]
cues: [road, place, number, landmark]
method: a vision model invents plausible names; every read label must be confirmed by a second reader or a reference before it anchors
tags: [hallucination, vision model, confirmation, second reader, OCR agreement, gazetteer check, model sees never places]
see: [reading-text-spotting, verify-evidence-families, failure-modes-catalogue]
---
Vision models complete what they expect: a half-legible "...ngton Road" becomes "Wellington Road", a town plan of
one city gets the street names of a more famous one, a scale bar in chains is read in metres, a north arrow is
reported "up" because it usually is. Guards: a label used as an anchor must be found by two readers (model and OCR,
or two model calls on different crops) or exist in the reference for the candidate area; a name found by the model
alone and absent from every gazetteer of the region is kept as text but not as a cue; the count of confirmed
labels, not the count of read labels, is what the policy sees. Two readings by two models of the same sheet are one
evidence family (both see the same ink); a reading and a register lookup are two. The model never places: it does
not estimate coordinates, it does not say "this looks like the east side of town", the matchers do that from data.
A reading that disagrees with the record (the drawing says one street, the record another) is kept with both: the
disagreement is a fact for the policy and often the sign of a mis-filed sheet.
