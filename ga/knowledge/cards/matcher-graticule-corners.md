---
id: matcher-graticule-corners
kinds: [historical_map]
cues: [grid]
method: graticule corner and tick reading to control points, polynomial fit
tags: [graticule, neatline, ticks, corner coordinates, control points, frame detection, Hough lines]
see: [family-survey-graticule, failure-one-line-off, transforms-choice-and-gcps]
primitives: [graticule_frame, graticule_frame_bounds, control_point_fit, residual_check]
buildable: yes
effort: in the library; a variant for a new frame style is hours
ingredients: the sheet image; the read corner values and interval; numpy and OpenCV line detection
---
Implementation that works: find the neatline as the longest near-horizontal and near-vertical dark lines enclosing
the map face (Hough or projection profiles after a threshold), then the tick marks or graticule lines inside it at
the read interval; intersect them into a lattice; assign each node its lon/lat from the corner values and the
interval; fit a 2nd-order polynomial with normalised coordinates; report the residual at every node. Two frame
conventions exist: the graticule drawn across the face (lines to intersect) and ticks on the neatline only (lines
to construct from opposite ticks). Two image conventions exist: the paper scan (longitude squeezed by cos(lat), a
tick spacing ratio to check) and the raster already resampled to degrees (1:1 aspect); try both and keep the one
whose lattice fits the detected lines. The classic failure is a lattice shifted by one interval with a perfect
residual; the guard is the number of lines found against the number expected from the corners, and an independent
family afterwards. When the frame reader finds no lines, the reader's corner values with the image rectangle still
give a four-point affine as a weak hypothesis, marked so.
