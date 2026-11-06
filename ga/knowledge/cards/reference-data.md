---
id: reference-data
kinds: [any]
cues: [road, place, number, grid]
method: which reference to retrieve
---
Great Britain: OS Open Names (places, roads), the address register (points per address), OS Zoomstack (roads, rail,
water, buildings, OpenData), OS topographic faces by WFS extract (licensed, per area). Elsewhere: OpenStreetMap by
Overpass (railways, canals, rivers, main roads, settlements; the slow-changing skeleton matches maps a century old);
Overpass mirrors fail often, retry across mirrors and cache by bounding box. Render references black-on-white at the
image's metric resolution; paint out printed graticules before structure matching, the reference has none.
