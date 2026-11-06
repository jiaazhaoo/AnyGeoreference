---
id: family-aerial-vertical
kinds: [raster_no_text]
cues: [landmark]
method: near-vertical aerial photographs fit a projective transform over flat ground; relief needs an orthorectification
tags: [aerial photograph, vertical, fiducial, focal length, flying height, orthophoto, relief displacement, DEM, homography, RAF, USGS single frame]
see: [family-oblique-photos, matcher-learned-image, matcher-polyline-shape, transforms-choice-and-gcps]
---
A vertical aerial photograph is a perspective image, not a map. Over flat ground it is a projective transform (8
parameters, four control points) of the ground; over relief every point is displaced radially from the nadir by
h/H times its distance from the nadir (h height above datum, H flying height), so a 100 m hill at 3,000 m flying
height moves a point at the edge of a 23 cm frame by about 1/30 of its radius: tens of metres on the ground. Photo
scale is focal length over flying height (a 152 mm lens at 3,000 m gives 1:20,000). The fiducial marks on the frame
edge give the principal point; the sortie number, frame number and date in the margin or the archive index give the
flight line and a candidate area. Method: find the area from the index or from a coarse landmark read (a town, a
river confluence), then match roads, field boundaries and water edges to a modern orthophoto or to a vector layer
with a learned matcher (photo to orthophoto is same-modality, the generic matchers work), fit a projective transform
with RANSAC, and verify by overlay of long linear features. For accurate work over relief, orthorectify with a DEM
and camera parameters instead of fitting a homography; say which was done. Vegetation and buildings changed, roads
and rivers mostly did not; prefer them. Expect 5-20 m from a homography on gentle ground, worse at the edges.
