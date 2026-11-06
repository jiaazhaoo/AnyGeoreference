---
id: failure-rotation-and-mirror
kinds: [any]
cues: [arrow, text]
method: scans arrive rotated by quarter turns and negatives mirrored; resolve orientation before matching, by the text
tags: [rotation, quarter turn, 90 degrees, 180, mirror, negative, microfiche, text direction, orientation]
see: [reading-orientation-and-scale, transforms-paper-and-scan-distortion, family-atlas-pages-insets]
---
A landscape sheet scanned portrait, a microfiche frame read from the wrong side, a photograph with its EXIF
orientation ignored: the matcher then finds a confident pose that is wrong by a quarter turn or a reflection,
because road networks and coastlines are nearly as plausible mirrored. Resolve orientation first and cheaply: the
direction in which most text reads (an OCR pass on the four rotations, the one with the most dictionary words
wins, and a mirrored page reads nothing), the north arrow, the position of the title (top) and the scale bar
(bottom), the series' convention. Then search rotation only within a few degrees of the resolved one, and never
allow a negative determinant in the fit unless mirroring was found by the text test. Negatives are inverted before
reading; a reader given a negative hallucinates. Record the orientation operation applied so the transform chain
starts from the raw scan.
