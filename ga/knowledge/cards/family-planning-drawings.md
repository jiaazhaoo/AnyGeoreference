---
id: family-planning-drawings
kinds: [planning_drawing]
cues: [road, number, place, arrow, scale]
method: site and location plans place by road names and house numbers against an address register, else by a learned matcher
tags: [site plan, location plan, block plan, planning application, red line, 1:1250, 1:500, house numbers, north arrow, scale bar]
see: [matcher-text-anchors, matcher-learned-image, reading-site-marking, verify-address-in-footprint]
primitives: [ocr_cached, road_and_place_labels, gazetteer_search, text_anchor_fit, address_in_footprint, plan_minima_match]
---
Planning drawings (site plans, location plans, block plans) are extracts of a large-scale base map, 1:500 to
1:2,500, with the application site marked in red, a north arrow, a scale bar or ratio, and the surrounding road names
and house numbers; the file usually comes with a record (an address, a reference). Three sub-kinds: location plans
with several road names and numbers (text anchors work), site plans with one road name and a shape (the learned
matcher against the base map round the address point is the method), and drawings with no location cue at all
(floor plans, elevations, sections, setting-out plans: abstain, nothing on them places them). Read with a vision
model: hand lettering, rotated labels and tiny digits defeat OCR. The record's address gives the candidate area; the
house numbers x road names pairs matched to address points give control points; RANSAC similarity, three inliers
suffice, eleven of twelve is strong; reject fits whose metres per pixel fall outside 2 mm to 2 m. Accept only with
the address point inside the fitted footprint; the matcher's own score accepted a 736 m miss on graded drawings. A
drawing may be rotated (north arrow not up), traced from an old edition (buildings differ), or a crop of a crop.
Deliverable: the site polygon in the national CRS, not just the sheet's transform.
