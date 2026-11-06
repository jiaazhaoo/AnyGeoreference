---
id: reading-text-spotting
kinds: [any]
cues: [road, place, number, text]
method: map text is rotated, curved, spaced and hand-lettered; a vision model reads it, OCR confirms it, both keep boxes
tags: [text spotting, OCR, PaddleOCR, Tesseract, vision model, rotated text, curved labels, letter spacing, mapKurator, MapText, label placement, toponym recognition]
see: [reading-hallucination-guard, reading-the-sheet, reference-gazetteers, literature-historical-map-georeferencing]
primitives: [ocr_cached, ocr_words, road_and_place_labels, claude_read]
---
Map text breaks document OCR: labels run along roads and rivers at any angle, river names are spaced letter by
letter across kilometres, town names are sized by population, old sheets are hand-lettered or engraved in copperplate
with long s and ligatures, and the lettering overlaps linework. Practice: a vision model reads the names (it handles
rotation, hand lettering and context) and returns a box per label; a text spotter or OCR run on the rotated page
and on label crops confirms the string and tightens the box; a name both found is a strong cue, a name only the
model found is a weak cue until a gazetteer confirms it. Digits are the risk: 3/8, 1/7, 0/6/9 and 5/6 swap in small
type and house numbers are all digits; keep the alternatives and let the matcher choose the reading that fits.
Normalise before lookup: case, abbreviations (St, Rd, Ave, Gt, Upr, Lr), apostrophes, hyphens, "The", and old
spellings. Label placement is a convention the matcher can use: a road name is written along the road, a town name
beside its symbol (usually to the right), a river name along the water, an area name spaced across the area; so
the label box is on or beside the feature, within one text height. Dedicated spotters trained on historical maps
exist (the text-spotting pipeline used on the Rumsey collection extracted 100 million labels from 60,000 maps) and
a public competition benchmark for map text exists since 2024; a map-text spotter is a buildable reader primitive.
