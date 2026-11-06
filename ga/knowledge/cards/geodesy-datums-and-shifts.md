---
id: geodesy-datums-and-shifts
kinds: [historical_map]
cues: [grid]
method: printed coordinates sit on the survey's datum; a uniform offset of tens to hundreds of metres against WGS84 is the datum, not an error
tags: [datum, OSGB36, ED50, NAD27, NAD83, Everest 1830, Tokyo datum, Bessel, Potsdam, Helmert, NTv2, OSTN15, WGS84, uniform offset]
see: [family-survey-graticule, transforms-residual-diagnostics, geodesy-prime-meridians-and-units]
primitives: [datum_shift]
buildable: yes
effort: hours; pyproj carries the Helmert parameters and shift grids
ingredients: pyproj with the EPSG database; the sheet's datum from the marginalia or the series' era
---
Latitude and longitude printed on a sheet are on the datum of the survey that made it, and treating them as WGS84
places the sheet wrong by a constant: OSGB36 (Great Britain, printed lat/lon on all 20th-century sheets) by up to
about 120 m; ED50 (European sheets 1950-1990) by 100-200 m; NAD27 (USA before 1983) by 10-100 m across the
contiguous states, more in Alaska and Hawaii; Everest 1830 and its Indian variants (South Asia) by several hundred
metres; Tokyo datum (Japan before 2002) by about 400 m; Bessel and Potsdam (Germany, central Europe) by 100-200 m;
local observatory datums on old charts by anything up to a kilometre. Grid coordinates on a national grid carry no
such problem when delivered in that grid's own CRS (EPSG:27700 is OSGB36 already). Diagnosis: a datum error is the
same vector at every control point (the residuals after a translation vanish); a misread point is one outlier; a
wrong projection grows from the centre out. Practice: read the datum from the margin or infer it from the series and
era, transform with the published Helmert parameters or shift grid (pyproj has them; for Britain the grid
transformation is accurate to a metre, the 7-parameter Helmert to a few metres), and keep both the printed-datum
transform and the shifted one in the delivery. Archives often publish their georeferenced copies still on the
printed datum: an archive bound disagreeing with a shifted placement by the known datum vector confirms the
placement rather than refuting it.
