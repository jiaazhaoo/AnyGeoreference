---
id: matcher-photo-landmarks
kinds: [raster_no_text]
cues: [landmark]
method: recognised landmarks locate a photograph to a town and a bearing; a Candidate, never a transform
tags: [landmark recognition, photograph, viewpoint, bearing, locate, Wikidata landmarks, visible from, not a transform]
see: [family-oblique-photos, family-aerial-vertical, reference-gazetteers, operate-abstention-reasons]
buildable: yes
effort: hours: landmark names from the reader, gazetteer and Wikidata positions, intersection of bearings or simply the cluster as a Candidate with a radius
ingredients: the reader's landmark cues; a gazetteer with landmarks (Wikidata, national names set); shapely
---
A photograph with a recognisable cathedral, bridge, stadium or hill is located by those landmarks: look each up,
take the cluster, and if three or more are visible estimate the viewpoint as the place from which their directions
match the image's left-to-right order (a resection on bearings, rough but honest). The product is a Candidate with
a centre and a radius and the list of landmarks with positions, delivered as "located", with the georeferencing
abstained for an oblique view (reason: perspective) and continued with a projective fit only for a near-vertical
view over flat ground. This is also the coarse stage for an aerial photograph with no index: the landmarks give the
candidate area, the roads and water edges give the fit. The reader names landmarks; it never estimates where the
camera was in coordinates.
