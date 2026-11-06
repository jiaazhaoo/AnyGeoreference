---
id: operate-cost-and-time
kinds: [any]
cues: []
method: what each step costs, what to cache, where the caps sit
tags: [cost, time, budget, cache, GPU minutes, reader calls, Overpass, cap, per sheet, per batch]
see: [operate-stopping, routing-coarse-to-fine, reference-licensing-and-privacy]
---
Orders of magnitude per sheet: a reading by a hosted vision model, cents and 10-60 seconds; a gazetteer or address
lookup, free and milliseconds from a local store, seconds over the network; a street-name locate-and-fit, seconds
on a CPU; a graticule fit, seconds; a correlation sweep, seconds to a minute; a learned matcher, 1-7 minutes of GPU
at 100 windows and far longer on a CPU; a batch plan by the main agent, one call; a built primitive, one session
of 10-25 minutes once, then free. Cache everything by request hash (reader calls, reference queries, rendered
tiles, matcher results) so a rerun of a batch costs nothing and reproduces; a planner experiment on ten drawings
made 88 calls and repeated none. Caps are per batch and per sheet (money and minutes), set in the plan, enforced
by the loop, and reported in the delivery next to the evidence; a batch that hits its cap is delivered as
incomplete with what was placed. Spend the GPU only after the funnel has a candidate area, and never on a sheet
whose reading has no cue. Three similar sheets cost three readings, one plan, one pilot and two checks; one sheet
costs the same minus the agreement it cannot have.
