---
id: geodesy-crs-and-outputs
kinds: [any]
cues: []
method: deliver an explicit CRS, the transform as GCPs plus model, a footprint, and standard files others can open
tags: [EPSG, CRS, 27700, 4326, 3857, UTM, GeoTIFF, world file, GCPs, gdal_translate, gdalwarp, IIIF Georeference Annotation, Allmaps, interchange]
see: [operate-delivery-contents, transforms-choice-and-gcps, geodesy-datums-and-shifts]
---
Name the CRS by EPSG code and never leave it implied: 27700 for the British National Grid, 4326 for lon/lat on
WGS84, 3857 only for web display, a UTM zone (326xx north, 327xx south) for anywhere else without a national grid.
Deliver the transform in the form that keeps the evidence: the control points (sheet px, CRS x/y, residual, source
cue) and the model fitted (similarity, affine, polynomial order, TPS), from which anyone regenerates the warp; the
six affine coefficients as a world file or GeoTIFF transform when the model is affine; a footprint polygon of the
sheet (and of the site, on drawings) in the CRS. Standard commands reproduce the raster: gdal_translate with -gcp
lines then gdalwarp with -order 1/2/3 or -tps and a resampling method; a GeoTIFF with GCP tags carries the points
inside the file. For archives and viewers, the IIIF Georeference Annotation (a Web Annotation with the image, the
control points and the transformation type, used by Allmaps and adopted as an IIIF extension in 2023) is the
interchange that lets any viewer warp the image from the same points. Record the datum of the printed coordinates
and whether a shift was applied. A delivery without residuals, CRS and the point list is not reproducible and is
not finished.
