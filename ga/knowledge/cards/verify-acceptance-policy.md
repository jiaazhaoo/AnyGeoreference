---
id: verify-acceptance-policy
kinds: [any]
cues: []
method: acceptance is a measured rule table with a frozen benchmark, calibration and a gate, not a threshold someone liked
tags: [policy, rule table, calibration, isotonic, PAV, Wilson interval, frozen benchmark, gate, McNemar, selective prediction, abstain band, accepted-wrong rate]
see: [verify-evidence-families, truth-audit, truth-tolerance-by-scale, literature-llm-geo]
---
A policy is a table of rules, each a condition on the facts of a placement (best score, matcher, residual, number
of families agreeing, address inside, places inside, margin above chance) and an action (accept, review, abstain),
evaluated in order with the trail of fired rules kept on the result. Each rule carries its measured accepted-wrong
rate on a frozen benchmark with a Wilson interval, and a probability from a calibrator (isotonic regression on the
benchmark's outcomes) so a delivery says 0.97, not "high". The benchmark is frozen with its truth bound to the
artefact digests, split into a development part and a holdout, and a change to the policy or a matcher is gated:
missed errors on the holdout must not rise above the baseline (paired test), the actions on frozen cases must not
move without a recorded reason. An abstain band exists on purpose: the cases between accept and review where the
facts say nothing, delivered as abstentions with the reason, counted as cost and not as errors. What this buys:
the accepted-wrong rate is a number with an interval, a new matcher proves itself on the same cases as the old, and
"the model said so" is never a rule. Measured: on six survey sheets the old policy (residual only) accepted six and
three were wrong; the two-family policy accepted three, all right, and sent the three bad reads to review.
