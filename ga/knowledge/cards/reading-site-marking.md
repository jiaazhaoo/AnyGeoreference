---
id: reading-site-marking
kinds: [planning_drawing]
cues: [text, landmark]
method: the site marking is the deliverable on a drawing: a red line, hatching, a thick outline, a label "site"
tags: [red line, site boundary, hatching, blue line, application site, polygon, deliverable, segmentation]
see: [family-planning-drawings, verify-address-in-footprint, truth-audit]
---
On planning drawings the object of interest is not the sheet but the site: the application boundary drawn in red
(blue for land in the same ownership), or hatched, or outlined thicker than the base map, sometimes only labelled.
The reader finds it as a pixel polygon (a ring, closed, inside the sheet); after the sheet is placed, the ring is
transformed to the CRS and delivered. Two judgements are separate: is the sheet placed right (the transform), and is
the ring the right site (the marking read). A right transform with the wrong ring (the neighbour's plot, the wider
ownership boundary, a hatched building instead of the plot) is a wrong delivery; the verification families for the
ring are the address point inside it, its area against the plot size in the address register, and its agreement with
the base-map parcel outline it should follow. Old drawings traced from an earlier base map have rings that follow
boundaries that moved; deliver the ring as drawn, snap to the current parcel only as a stated option. A drawing with
no marking at all (a location plan that only shows where the site is by an arrow) delivers a point, not a polygon.
