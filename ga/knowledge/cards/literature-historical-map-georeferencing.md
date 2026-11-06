---
id: literature-historical-map-georeferencing
kinds: [historical_map, street_map]
cues: [place, road, grid]
method: what the historical-map literature established: text spotting at scale, toponym alignment, content-based georeferencing, standards for sharing control points
tags: [literature, historical maps, mapKurator, toponym alignment, content-based georeferencing, MapReader, Allmaps, IIIF, MapText competition, Rumsey, deformable part models]
see: [reading-text-spotting, matcher-toponym-constellation, geodesy-crs-and-outputs, literature-image-matching]
---
Established results. Toponym recognition and alignment (Weinman, 2013 and 2017): read the place names on a sheet,
align the pattern of names to a gazetteer, and the alignment both georeferences the sheet and corrects the
readings; the method of the toponym-constellation card. Content-based georeferencing of topographic series (Luft
and Schiewe, 2021; Uhl and colleagues on the USGS historical collection, 2021-2022): detect the map frame and the
grid or graticule, read corner coordinates, and place whole series automatically, with the one-line-off and
datum faults as the known residual error classes. Feature alignment by deformable part models (Howe and colleagues,
2019) and dense alignment of historical to modern maps by deep networks (2026 work on urban change) for sheets
whose linework, not text, carries the position. Text spotting on maps at scale: the pipeline run over the Rumsey
collection extracted and linked some 100 million labels from 60,000 maps (2023), with a public competition on
map text detection, recognition and linking since 2024; patch-level classification of series sheets (MapReader,
2022). Sharing: the IIIF Georeference Annotation, approved as an extension in 2023 and used by Allmaps, lets any
viewer warp an image from a published list of control points and a transformation type, with polynomial orders
one to three and thin plate spline. Surveys (Chiang, Duan, Leyk, Uhl, Knoblock, 2020) frame the field as
extraction plus alignment plus linking. What the literature does not supply and this system adds: a runtime
acceptance policy with measured accepted-wrong rates, typed abstention, and the planner that composes these
methods per batch.
