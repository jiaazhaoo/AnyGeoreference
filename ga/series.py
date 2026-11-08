"""A series whose printed coordinates are off in a way nearby sheets share (a local survey, a datum or a sheet
layout the record does not state), learned across a batch from an external reference and applied to the record.

Each sheet placed from its own reading and checked against OpenStreetMap's water gives an anchor: where its
reading puts the sheet relative to the world (the water shift, metres east and north, in the record's datum). Nearby
anchors of one series agree with each other when the error belongs to the series and not to the sheet; the field is
their locally weighted linear regression (robust, so a river that moved does not pull it). For a sheet whose own
water disagrees, the field is fitted WITHOUT that sheet, applied to the record's coordinates like a datum transform,
and the sheet is placed again; its own water check is then an independent test of the prediction.

The field never sees the truth. It is refused where the anchors around a point are too few, or where they do not
predict each other at least twice as well as "no correction" (leave-one-out): then there is no shared error to learn.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

KM_LON = 111.320          # km per degree of longitude at the equator
KM_LAT = 110.574


@dataclass(frozen=True)
class Anchor:
    key: str              # the case (all editions of one sheet share it: they are one measurement of one place)
    lon: float
    lat: float
    dx_m: float           # water shift: the world is this far east of where the reading put the sheet
    dy_m: float           # ... and this far north
    n: int = 1            # scans averaged


def anchors_from(key: str, lon: float, lat: float, shifts: list[tuple[float, float]]) -> list[Anchor]:
    """One anchor per sheet: the mean of its scans' water shifts (editions measure the same place)."""
    if not shifts:
        return []
    a = np.array(shifts, float)
    return [Anchor(key, lon, lat, float(a[:, 0].mean()), float(a[:, 1].mean()), len(a))]


def _km(lon, lat, lon0, lat0):
    return (np.asarray(lon) - lon0) * KM_LON * math.cos(math.radians(lat0)), (np.asarray(lat) - lat0) * KM_LAT


def _fit_at(anchors: list[Anchor], lon0: float, lat0: float, h_km: float, scale_m: float, iters: int = 3):
    """Local linear fit of (dx, dy) at (lon0, lat0): Gaussian weights of bandwidth h_km, Cauchy reweighting of
    anchors the plane does not explain (scale_m). Returns (coef_dx, coef_dy, n_eff) with coef = a + b X + c Y in metres,
    X and Y in km east and north of the point; or None if the anchors are too few to fit a plane."""
    if len(anchors) < 4:
        return None
    X, Y = _km([a.lon for a in anchors], [a.lat for a in anchors], lon0, lat0)
    D = np.c_[[a.dx_m for a in anchors], [a.dy_m for a in anchors]]
    w0 = np.exp(-(X ** 2 + Y ** 2) / (2 * h_km ** 2)) * np.array([a.n for a in anchors], float)
    A = np.c_[np.ones_like(X), X, Y]
    w = w0.copy()
    for _ in range(iters):
        if w.sum() <= 0:
            return None
        sw = np.sqrt(w)[:, None]
        coef, *_ = np.linalg.lstsq(A * sw, D * sw, rcond=None)
        r = np.linalg.norm(D - A @ coef, axis=1)
        w = w0 / (1 + (r / scale_m) ** 2)
    n_eff = float(w0.sum() ** 2 / max(1e-12, (w0 ** 2).sum()))
    if n_eff < 4 or np.linalg.matrix_rank(A[w0 > 1e-3 * w0.max()]) < 3:
        return None
    return coef[:, 0], coef[:, 1], n_eff


class SeriesField:
    """The batch's anchors and how well they predict each other. `predict` excludes the sheet asked about."""

    def __init__(self, anchors: list[Anchor], bandwidths_km=(15.0, 30.0, 60.0, 120.0), tol_m: float = 60.0,
                 min_eff: float = 6.0):
        self.anchors, self.bandwidths, self.tol_m, self.min_eff = list(anchors), tuple(bandwidths_km), tol_m, min_eff

    def _loo(self, anchors: list[Anchor], h: float) -> np.ndarray:
        """Each anchor predicted from the others (its own sheet left out): error in metres (nan where no fit)."""
        out = np.full(len(anchors), np.nan)
        for i, a in enumerate(anchors):
            rest = [b for b in anchors if b.key != a.key]
            f = _fit_at(rest, a.lon, a.lat, h, self.tol_m)
            if f is not None and f[2] >= self.min_eff:
                out[i] = math.hypot(f[0][0] - a.dx_m, f[1][0] - a.dy_m)
        return out

    def predict(self, lon: float, lat: float, exclude: str | None = None) -> dict | None:
        """The field at (lon, lat) from every anchor but `exclude`'s, with the bandwidth that predicts those anchors
        best (leave-one-out), or None: too few anchors near, or the anchors near do not predict each other within tol_m."""
        pool = [a for a in self.anchors if a.key != exclude]
        if len(pool) < 4:
            return None
        best = None
        for h in self.bandwidths:
            loo = self._loo(pool, h)
            X, Y = _km([a.lon for a in pool], [a.lat for a in pool], lon, lat)
            near = (np.hypot(X, Y) <= 2 * h) & ~np.isnan(loo)
            if near.sum() < 3:
                continue
            err = float(np.median(loo[near]))
            null = float(np.median([math.hypot(a.dx_m, a.dy_m) for a, k in zip(pool, near) if k]))
            if best is None or err < best[0]:
                best = (err, h, int(near.sum()), null)
        if best is None:
            return None
        err, h, n_near, null = best
        f = _fit_at(pool, lon, lat, h, self.tol_m)
        # the field must carry information: predict the anchors around here better than "no correction" does.
        # It need not be within tol_m: the sheet's own external check, which the field never saw, decides.
        if f is None or f[2] < self.min_eff or err >= 0.5 * null:
            return None
        return {"lon0": lon, "lat0": lat, "coef_dx": [round(float(v), 4) for v in f[0]], "coef_dy": [round(float(v), 4) for v in f[1]],
                "h_km": h, "n_eff": round(f[2], 1), "anchors_near": n_near, "loo_m": round(err, 1), "null_m": round(null, 1)}


def offset_at(field: dict, lon, lat) -> tuple[np.ndarray, np.ndarray]:
    """The field's (dx, dy) in metres at record coordinates (lon, lat)."""
    X, Y = _km(lon, lat, field["lon0"], field["lat0"])
    cx, cy = field["coef_dx"], field["coef_dy"]
    return cx[0] + cx[1] * X + cx[2] * Y, cy[0] + cy[1] * X + cy[2] * Y


def correct(field: dict, lon, lat) -> tuple[np.ndarray, np.ndarray]:
    """Record coordinates moved by the field: where the world is, in the record's datum."""
    lon, lat = np.asarray(lon, float), np.asarray(lat, float)
    dx, dy = offset_at(field, lon, lat)
    return lon + dx / (KM_LON * 1000 * np.cos(np.radians(lat))), lat + dy / (KM_LAT * 1000)
