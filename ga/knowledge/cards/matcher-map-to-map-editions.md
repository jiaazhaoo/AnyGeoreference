---
id: matcher-map-to-map-editions
kinds: [historical_map]
cues: [grid, text]
method: match a sheet to an already georeferenced edition of the same series and inherit its georeference, bias stated
tags: [map to map, edition, same series, inherit georeference, archive tiles, topoView, NLS, Rumsey, same symbology, cross edition agreement]
see: [family-historic-gb-series, reference-basemaps-and-rasters, matcher-render-and-correlate, verify-catalogue]
primitives: [cross_edition_agreement, structure_match]
buildable: yes
effort: half a day: fetch the georeferenced edition's tiles for the sheet's index box, match (correlation or a learned matcher, same style), chain the transforms, state the archive's accuracy as the bias
ingredients: an archive tile service or georeferenced raster of the same series (national library, USGS historical collection, a large digitised collection); the sheet number or a candidate area; numpy, OpenCV
---
The easiest match in the trade: the same series, the same symbology, a different edition or a different scan,
already georeferenced by an archive. Fetch the archive's raster over the sheet's box (from the index or a candidate
area), match sheet to raster (correlation works when the scale is close; a learned matcher tolerates a different
scan and revision), fit, and chain: sheet px -> archive px -> CRS. Inherit the archive's georeference as a truth
source of rank external authority with its known bias: archives often keep the printed datum, sometimes
georeference by corners only (tens of metres inside the sheet), and occasionally mislabel a sheet. So the
agreement between an edition-inherited placement and one from the sheet's own graticule is a strong two-family
accept, and their disagreement by a constant vector is usually the datum. Revisions between editions (new
railways, new suburbs) are added ink, not moved ink; the matcher ignores them. Where several editions exist, the
nearest in date matches best.
