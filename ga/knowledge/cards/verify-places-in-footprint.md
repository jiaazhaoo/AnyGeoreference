---
id: verify-places-in-footprint
kinds: [street_map, historical_map]
cues: [place, landmark]
method: names the fit did not use, found inside the footprint, verify a road fit; rare names count, common ones barely
tags: [places inside, held-out names, landmarks inside, rarity weight, second family for road fit]
see: [matcher-street-names-geometry, matcher-toponym-constellation, reference-gazetteers, verify-catalogue]
primitives: [places_in_footprint]
---
A fit made from street labels is verified by the place names and landmarks the fit never consumed: parks,
churches, stations, districts, pubs, schools read on the sheet and looked up in the gazetteer; two or more of them
inside the placed footprint, at the right side of it, is a second family. Weight by rarity: a district name that
exists once in the country is worth ten "Church Streets"; a name that occurs inside any 1 km footprint of the town
is worth nothing. Record which names were held out before the fit ran, so the verification cannot be accused of
reusing the fit's cues; when every readable name was needed for the fit (a sparse sheet), say so and use structure
instead. Measured on an 1823 town plan: the road fit placed the sheet 125 m from the archive's placement and three
held-out place names fell inside, accept; on a modern suburb render four of four, accept at 371 m, which also
measures how loose a 2 km footprint's "inside" is and why rarity and side matter.
