---
id: verify-address-in-footprint
kinds: [planning_drawing]
cues: [number, road]
method: the record's address point must fall inside the placed footprint, and not trivially
tags: [address inside, footprint, record address, trivially inside, footprint size, second family]
see: [family-planning-drawings, matcher-learned-image, verify-catalogue, reading-site-marking]
primitives: [address_in_footprint]
---
On a drawing with a record, the address point is a family the matcher did not use (the matcher used the drawn
structure or the labels; the record came from the file). The point inside the fitted footprint is the accept
condition that turned the learned matcher's score into something safe: with the score alone, one of three accepts
was 736 m off; with the point inside, two accepts, both right. The check must not be trivial: a footprint of two
kilometres contains the address by construction, so compute the footprint's size at the fitted scale and require it
to be in the family's range, and report the point's distance from the site marking as well as from the footprint
edge (the site should be near the address, within tens of metres on a site plan, within the plot on a location
plan). A record address outside the footprint with a good-looking fit is a mis-filed drawing or a wrong town, and
the delivery says "address outside footprint", a review, not a wrong placement accepted.
