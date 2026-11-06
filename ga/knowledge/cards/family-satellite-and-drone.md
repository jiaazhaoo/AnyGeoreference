---
id: family-satellite-and-drone
kinds: [raster_no_text]
cues: []
method: imagery usually arrives with its georeference in metadata; the job is to verify and tighten it, not to place from nothing
tags: [satellite, drone, orthomosaic, RPC, EXIF GPS, GeoTIFF tags, sensor model, co-registration, verify metadata]
see: [verify-catalogue, matcher-learned-image, geodesy-crs-and-outputs]
---
Satellite scenes carry rational polynomial coefficients or a sensor model; drone orthomosaics carry a GeoTIFF
transform from the flight's GNSS and ground control; a phone photo carries EXIF GPS of the camera, not of the
scene. For these the question changes from "where is this" to "is the stated georeference right and how far off".
Treat the metadata as a Hypothesis from the source "metadata" with the stated accuracy (RPC without ground control:
5-15 m for high-resolution sensors; consumer drone without GCPs: metres to tens of metres; EXIF: the camera's
position, not the image footprint). Verify by co-registration to a reference orthophoto or road layer (same
modality: the generic matchers work) and report the shift; tighten with a translation or a low-order correction
only when the shift is consistent across the scene. Never silently replace a stated georeference: the delivery
shows the stated one, the measured shift and the corrected one as three facts. Cloud, shadow and seasonal change
make local matches fail where the global shift is still right: aggregate over the scene before judging.
