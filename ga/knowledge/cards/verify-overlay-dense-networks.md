---
id: verify-overlay-dense-networks
kinds: [street_map, planning_drawing, raster_no_text]
cues: []
method: overlay agreement is weak where the network is dense; measure chance level with shifted poses and use orientation
tags: [overlay, dense network, chance level, shifted pose, orientation-aware chamfer, holdout, margin]
see: [verify-catalogue, matcher-polyline-shape, matcher-render-and-correlate]
primitives: [overlay_agreement]
buildable: yes
effort: hours: score the hypothesis and eight shifted copies (200 m, eight directions), report the margin; add line-orientation agreement
ingredients: the sheet's linework mask and the reference render already produced by the matcher; numpy, OpenCV
---
In a town centre a road is within 10 pixels of any point, so "share of sheet linework near reference linework" is
high for a wrong pose too: on a dense suburb render the overlay said 0.8 at the right pose and 0.7 at a pose 300 m
off. Fix the measure, not the threshold: score the same hypothesis shifted by 200 m in eight directions and report
the margin between the true pose and the best shifted one (a real placement wins by a wide margin, a chance one by
nothing); compare line orientations, not only positions (a road running north-south on the sheet should lie on a
north-south road, which halves the chance agreement); hold out a class (verify a road fit with water or rail, not
with roads). On a sparse rural sheet the plain overlay is fine and the margin is large; the measure adapts, the
rule stays "second family with a margin above chance".
