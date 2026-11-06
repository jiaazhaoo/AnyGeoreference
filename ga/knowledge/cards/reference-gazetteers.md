---
id: reference-gazetteers
kinds: [any]
cues: [place, landmark, text]
method: place names to positions: which gazetteer for which era and country, and how to disambiguate
tags: [gazetteer, OS Open Names, GeoNames, Wikidata, GNIS, GB1900, Vision of Britain, OpenHistoricalMap, toponym, disambiguation, densest cluster]
see: [matcher-toponym-constellation, reference-historic-epoch, reading-text-spotting]
primitives: [gazetteer_search, place_lookup]
---
Modern: national names datasets (Great Britain: OS Open Names, 2.9 million entries, settlements, roads, postcodes,
in EPSG:27700; USA: GNIS; most countries: an official names register), GeoNames worldwide with feature classes and
populations, Wikidata with coordinates for anything that has an article (churches, stations, country houses,
battlefields: the landmarks of old maps). Historical: GB1900 (every name on the OS six-inch 1888-1913 sheets,
transcribed twice and reconciled, with coordinates), Vision of Britain and historical administrative units,
OpenHistoricalMap, the names index of a georeferenced map collection. Disambiguation is the whole problem: one name
has many places (there are dozens of Newtons), so never geocode one name, geocode all of them and take the densest
cluster of co-occurring hits; weight by feature type (a city outweighs a farm) and by the name's rarity (a unique
name is worth ten common ones); use the record's region to cut the search. Feature types tell the matcher where the
point sits relative to the label: a settlement's point is its centre, a road's point is its midpoint, a parish's its
centroid; a town label placed beside the symbol is 1-2 text heights off the point. Store the lookup results with
the cue so a reader rerun does not redo the queries.
