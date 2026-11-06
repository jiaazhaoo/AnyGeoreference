---
id: matcher-text-anchors
kinds: [planning_drawing, street_map]
cues: [road, number, place]
method: road names and house numbers against an address register, RANSAC similarity
tags: [text anchors, address points, house numbers, road names, RANSAC, similarity, inliers, gazetteer seed]
see: [family-planning-drawings, reference-addresses, verify-address-in-footprint, matcher-street-names-geometry]
primitives: [ocr_cached, road_and_place_labels, gazetteer_search, text_anchor_fit, address_in_footprint]
buildable: yes
effort: in the library
ingredients: the reader's road and number cues; an address register with street and number; a gazetteer for the seed
---
Read the names (a vision model reads hand lettering OCR misses), find the record's street in a gazetteer to get a
candidate area, pair each house number with the nearest road label on the sheet, look up number x road in the
address register inside the area, and fit a similarity by RANSAC over the pairs; three inliers suffice, eleven of
twelve is a strong fit. Reject fits whose metres per pixel fall outside 2 mm to 2 m (a degenerate fit gives scale 0)
or whose rotation contradicts a read north arrow by more than 15 degrees. Verify with the address point inside the
footprint and, where the sheet has them, with place names or landmarks inside the footprint that were not anchors.
Digit misreads are handled by keeping alternatives per number and letting RANSAC choose. Sheets without numbers go
to the street-name geometry matcher (names only) or the learned matcher (structure); sheets with no location cue at
all (floor plans, setting-out plans, sections) cannot be placed: abstain and say so.
