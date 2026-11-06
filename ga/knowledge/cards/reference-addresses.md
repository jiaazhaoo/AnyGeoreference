---
id: reference-addresses
kinds: [planning_drawing, street_map]
cues: [number, road]
method: house number x street to a point; the sharpest anchor there is on a large-scale sheet
tags: [address register, AddressBase, OpenAddresses, UPRN, house numbers, odd even, number ranges, privacy]
see: [matcher-text-anchors, verify-address-in-footprint, reference-licensing-and-privacy]
primitives: [text_anchor_fit, address_in_footprint]
---
An address register (a national licensed one, or open address sets where they exist) gives a point per numbered
building; a house number read next to a street name on a 1:500-1:2,500 sheet is a control point to a few metres,
the sharpest anchor a drawing has. Use the conventions: odd numbers on one side, even on the other, ascending away
from the town centre; so a read "23" beside "Mill Street" with "25" further along fixes the side and the direction,
and a number that fits the sequence but not the register is probably a misread digit. Three matched numbers fix a
similarity; a dozen with eleven inliers is a strong fit; one number alone is a candidate area of a few hundred
metres. The record's own address gives the candidate area before any reading. Numbering changed on old streets
(renumbering after infill, demolished runs), so on old sheets numbers confirm, they do not anchor. Addresses are
personal data: they stay in the reference store, never in a public output, a repository, a log or an example; a
delivery carries coordinates and the register's identifier, not the address text, unless the client asked for it.
