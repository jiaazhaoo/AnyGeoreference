---
id: reading-the-sheet
kinds: [any]
cues: [road, number, place, landmark, arrow, scale, grid, text]
method: what to read first and what a reading may not contain
tags: [reader, vision model, cues, pixel boxes, never coordinates, OCR, VLM]
see: [reading-marginalia, reading-text-spotting, reading-orientation-and-scale, reading-hallucination-guard]
primitives: [claude_read, ocr_cached, ocr_words, road_and_place_labels]
---
Read before computing: road names, house numbers, place names, landmarks (churches, stations, bridges, named
buildings), the north arrow (up, or rotated by how much), the scale (1:1250, 1/500, a bar in metres or chains),
printed grid figures or corner coordinates, the sheet number and series, the date, the site marking (red line,
hatching). A reading returns pixel boxes on the sheet and never coordinates on the Earth: the model sees, the tools
compute. Page-wide words (title block, notes, collar) help retrieval and tell the series and era; only words on the
map face itself may anchor a placement. Ask for every street name, not the main ones: a street-name matcher with
forty names is unambiguous, with five it is a guess. Keep the reader's boxes; a label's anchor is where the name is
written along its feature, not the centre of a loose box. A reader that finds no location cue has answered:
nothing on this sheet places it, and that answer is delivered, not worked around.
