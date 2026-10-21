"""Geometry helpers: polyline decoding, distances, and checkpoint sampling."""

from __future__ import annotations

import math
from bisect import bisect_left
from dataclasses import dataclass

EARTH_RADIUS_MI = 3958.8

LonLat = tuple[float, float]


def decode_polyline(encoded: str, precision: int = 6) -> list[LonLat]:
    """Decode a Google-style encoded polyline (Valhalla uses precision 6)."""
    coords: list[LonLat] = []
    index = lat = lon = 0
    factor = 10**precision
    while index < len(encoded):
        deltas = []
        for _ in range(2):
            shift = result = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat += deltas[0]
        lon += deltas[1]
        coords.append((lon / factor, lat / factor))
    return coords


def haversine_mi(a: LonLat, b: LonLat) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(h))


def cumulative_miles(coords: list[LonLat]) -> list[float]:
    out = [0.0]
    for a, b in zip(coords, coords[1:]):
        out.append(out[-1] + haversine_mi(a, b))
    return out


def interpolate(xs: list[float], ys: list[float], x: float) -> float:
    """Piecewise-linear interpolation of y at x (xs ascending)."""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    i = bisect_left(xs, x)
    x0, x1 = xs[i - 1], xs[i]
    t = 0.0 if x1 == x0 else (x - x0) / (x1 - x0)
    return ys[i - 1] + t * (ys[i] - ys[i - 1])


def point_at(coords: list[LonLat], cum: list[float], mile: float) -> LonLat:
    if mile <= 0:
        return coords[0]
    if mile >= cum[-1]:
        return coords[-1]
    i = bisect_left(cum, mile)
    seg = cum[i] - cum[i - 1]
    t = 0.0 if seg == 0 else (mile - cum[i - 1]) / seg
    (x0, y0), (x1, y1) = coords[i - 1], coords[i]
    return (x0 + t * (x1 - x0), y0 + t * (y1 - y0))


@dataclass(frozen=True)
class Sample:
    mile: float
    lonlat: LonLat
    elapsed_s: float


def sample_route(
    coords: list[LonLat],
    time_profile: tuple[list[float], list[float]],
    interval_mi: float,
) -> list[Sample]:
    """Checkpoints at the origin, every `interval_mi`, and at the destination.

    `time_profile` is (miles, elapsed seconds) pairs from the routing provider, so
    ETAs follow the provider's speed per road segment instead of a flat average.
    The geometry's own length is rescaled to the provider's reported length so the
    two mileage scales agree.
    """
    cum = cumulative_miles(coords)
    prof_miles, prof_secs = time_profile
    total = prof_miles[-1]
    scale = cum[-1] / total if total else 1.0

    marks = [0.0]
    m = interval_mi
    while m < total - 1e-6:
        marks.append(m)
        m += interval_mi
    if total - marks[-1] > 1e-6:
        marks.append(total)

    return [
        Sample(
            mile=mark,
            lonlat=point_at(coords, cum, mark * scale),
            elapsed_s=interpolate(prof_miles, prof_secs, mark),
        )
        for mark in marks
    ]


def bbox(coords: list[LonLat]) -> tuple[float, float, float, float]:
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    return min(xs), min(ys), max(xs), max(ys)


def simplify_for_distance(coords: list[LonLat], step_mi: float) -> list[LonLat]:
    """Thin a polyline to roughly one vertex every `step_mi` (for corridor tests)."""
    out = [coords[0]]
    acc = 0.0
    for a, b in zip(coords, coords[1:]):
        acc += haversine_mi(a, b)
        if acc >= step_mi:
            out.append(b)
            acc = 0.0
    out.append(coords[-1])
    return out
