---
id: operate-evaluation-design
kinds: [any]
cues: []
method: the main agent designs the evaluation before running: metrics, tolerance, split, truth, and what would make it stop
tags: [evaluation design, metrics, placed right wrong abstained, calibration, cost, split, pilot check, holdout, stop criterion, improvement loop]
see: [verify-acceptance-policy, truth-sources, truth-tolerance-by-scale, operate-stopping, routing-input-contract]
---
An evaluation is designed before the first matcher runs, from the plan: which truth will judge (ranked), at what
tolerance (the task's bar, above the map's floor), on which split (pilot sheet versus check sheets; development
versus holdout on a benchmark), with which metrics (placed right, placed wrong, abstained by reason, review rate,
calibration error, cost per sheet, minutes per sheet) and with which stop criterion (accepted-wrong at zero on the
check sheets with the interval reported; or the dominant abstention reason named, which is the next build). The
loop then runs, measures, and feeds back: a dominant no_fit reason asks for a matcher, a dominant unverified asks
for a verification family or a reference, a wrong placement asks for a stricter rule or a new family, a cost
overrun asks for an earlier funnel stage. Each change is gated on the frozen cases (missed errors must not rise)
and the evaluation is rerun; the loop stops when the stop criterion holds or when a change fails to move the
dominant reason, which is reported as a finding rather than retried. Negative results are kept with their numbers;
they are what stops the next version from trying the same thing.
