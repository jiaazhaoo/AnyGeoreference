---
id: matcher-toponym-constellation
kinds: [historical_map, street_map]
cues: [place, landmark]
method: place names only, no roads: match the pattern of named points to the gazetteer by pairwise geometry, then fit a similarity
tags: [toponym, constellation, geometric hashing, point pattern, place names, gazetteer alignment, no roads, small scale, county map]
see: [reference-gazetteers, family-small-scale-thematic, family-cadastral-estate, matcher-street-names-geometry]
buildable: yes
effort: one day: candidate generation by name clusters, pairwise-distance-ratio voting over triples, similarity fit by RANSAC, places-inside verification
ingredients: a gazetteer with feature types (national names set, GeoNames, a historical transcription); the reader's place cues with boxes; numpy, shapely
---
Many sheets name places but no streets: county maps, small-scale sheets, estate maps naming farms and hamlets,
charts naming headlands. The names are points, and a set of named points is a constellation whose shape does not
depend on scale or rotation. Method: for every read name take all gazetteer hits in the region (hundreds for common
names); for every pair of read names and every pair of their hits, the ratio of pixel distance to ground distance
is a scale vote and the angle difference a rotation vote; accumulate votes in a scale-rotation histogram, take the
peak, and keep the hits consistent with it; then fit a similarity by RANSAC over the consistent name-hit pairs and
count inliers. Three consistent names place a sheet; six make it certain; feature types prune (a city label is not
a farm). Rarity weights the votes: a unique name is worth ten Newtons. Label offset is a known bias (the point is
1-2 text heights from the label, usually left of it), so the tolerance is a few text heights, not pixels. Verify
with names the fit did not use (held out) found inside the footprint, or with structure. This is the classic
toponym-alignment method of the historical-map literature (gazetteer alignment, 2013 onward); it is the floor for
every text-bearing sheet without streets, and the planner should ask for it whenever place cues outnumber road
cues.
