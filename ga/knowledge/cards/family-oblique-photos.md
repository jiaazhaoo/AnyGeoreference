---
id: family-oblique-photos
kinds: [raster_no_text]
cues: [landmark]
method: an oblique photograph is located (viewpoint, view direction, visible landmarks), not georeferenced; a homography holds for one ground plane only
tags: [oblique, perspective, horizon, viewpoint, camera pose, landmark recognition, photogrammetry, 3D, not georeferenceable]
see: [family-aerial-vertical, matcher-photo-landmarks, operate-abstention-reasons]
buildable: no
effort: single-image pose over 3D terrain needs a DEM, building models and a camera model; out of scope for a raster-to-map transform
---
An oblique photograph (a view from a hill, a tower, a low-flying aircraft, a drone looking forward) has no single
transform to the map: every height is a different ground plane, the scale changes along the view, the horizon is at
infinity. What can be delivered honestly: the viewpoint (where the camera stood, from the landmarks visible and their
relative directions), the view direction, and the list of recognised landmarks with their map positions; or a
homography for one ground plane (a flat square, a field) that is valid for that plane only, stated as such. What
cannot: a footprint polygon for "the image". A reader that names the cathedral, the river bridge and the stadium
has located the photograph to a town and a bearing; that is a Candidate with a radius, not a Hypothesis with a
transform, and the system delivers it as a located image with an abstention from georeferencing, reason
"oblique perspective". Full camera pose from one image needs a terrain and building model and a camera model;
that is photogrammetry, a different tool, and the plan says so instead of forcing a fit.
