"""Turns raw routes + forecasts into scored route options and a recommendation."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .geo import LonLat, bbox, haversine_mi, sample_route, simplify_for_distance
from .providers import directions, weather
from .risk import Risk, assess, risk_score

HEATMAP_HOURS = 48
DISPLAY_STEP_MI = 0.5  # thin route geometry sent to the browser


@dataclass
class RouteOption:
    index: int
    route: directions.Route
    checkpoints: list[dict]
    miles_by_level: dict[int, float]
    avg_risk: float
    recommended: bool = False
    rank: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def sort_key(self) -> tuple:
        """The brief's preference order. No Travel miles come first because they
        are strictly worse than Severe. Values are rounded only to absorb float
        noise, at the same precision the API reports them."""
        return (
            round(self.miles_by_level[Risk.NO_TRAVEL], 1),
            round(self.miles_by_level[Risk.SEVERE], 1),
            round(self.miles_by_level[Risk.HIGH], 1),
            round(self.avg_risk, 2),
            self.route.duration_s,
        )

    def as_dict(self) -> dict:
        r = self.route
        return {
            "index": self.index,
            "rank": self.rank,
            "recommended": self.recommended,
            "source": r.source,
            "distance_mi": round(r.distance_mi, 1),
            "duration_s": round(r.duration_s),
            "avg_risk": round(self.avg_risk, 2),
            "max_risk": max(cp["risk"]["level"] for cp in self.checkpoints),
            "miles_by_level": {Risk(k).label: round(v, 1) for k, v in self.miles_by_level.items()},
            "notes": self.notes,
            "geometry": simplify_for_distance(r.coords, DISPLAY_STEP_MI),
            "checkpoints": self.checkpoints,
        }


def _score_route(index: int, route: directions.Route, departure: datetime, load_lb: float,
                 interval_mi: float, forecasts: dict) -> RouteOption:
    samples = sample_route(route.coords, route.time_profile, interval_mi)
    checkpoints = []
    for s in samples:
        eta = departure + timedelta(seconds=s.elapsed_s)
        wx = weather.lookup(forecasts, s.lonlat).at(eta)
        a = assess(wx["wind_mph"], wx["rain_in_hr"], wx["snow_in_hr"], load_lb)
        checkpoints.append({
            "mile": round(s.mile, 1),
            "lon": round(s.lonlat[0], 5),
            "lat": round(s.lonlat[1], 5),
            "eta": eta.isoformat(),
            "elapsed_s": round(s.elapsed_s),
            "weather": {k: round(v, 2) for k, v in wx.items()},
            "risk": a.as_dict(),
        })

    # Each stretch between two checkpoints takes the worse of its two ends: we
    # only know the weather at the samples, and for a safety tool it is better to
    # over- than under-count dangerous miles.
    miles = {lvl: 0.0 for lvl in Risk}
    for a, b in zip(checkpoints, checkpoints[1:]):
        lvl = Risk(max(a["risk"]["level"], b["risk"]["level"]))
        miles[lvl] += b["mile"] - a["mile"]
    total = sum(miles.values()) or 1.0
    avg = sum(lvl * m for lvl, m in miles.items()) / total

    option = RouteOption(index, route, checkpoints, miles, avg)
    if route.via is not None:
        option.notes.append("Alternative generated through a detour waypoint")
    return option


def _explain(best: RouteOption, runner_up: RouteOption | None) -> str:
    if runner_up is None:
        return "Only one route was available."
    labels = ("No Travel miles", "Severe miles", "High miles", "average risk", "travel time")
    for label, mine, theirs in zip(labels, best.sort_key, runner_up.sort_key):
        if mine != theirs:
            if label == "travel time":
                return f"Same weather exposure as the next option, and {(theirs - mine) / 60:.0f} min faster."
            if label == "average risk":
                return f"Lowest average risk ({best.avg_risk:.2f} vs {runner_up.avg_risk:.2f})."
            return f"Fewest {label} ({mine:g} vs {theirs:g})."
    return "Tied with the next option on every criterion."


def plan_routes(origin: LonLat, dest: LonLat, departure: datetime, load_lb: float, interval_mi: float,
                weather_data: dict | None = None) -> dict:
    routes = directions.get_alternatives(origin, dest, load_lb)

    # One forecast window covering the longest trip, fetched once for every
    # checkpoint of every route.
    # Same 48 h window the heatmap uses, so both share cache entries.
    hours = max(HEATMAP_HOURS, math.ceil(max(r.duration_s for r in routes) / 3600) + 1)
    all_samples = [s.lonlat for r in routes for s in sample_route(r.coords, r.time_profile, interval_mi)]
    forecasts = weather.hourly_forecasts(all_samples, departure, hours, weather_data)

    options = [_score_route(i, r, departure, load_lb, interval_mi, forecasts) for i, r in enumerate(routes)]
    ranked = sorted(options, key=lambda o: o.sort_key)
    for rank, o in enumerate(ranked, start=1):
        o.rank = rank
    best = ranked[0]
    best.recommended = True

    warning = None
    if best.miles_by_level[Risk.NO_TRAVEL] > 0:
        warning = "Every route crosses No Travel conditions at the planned time. Consider delaying departure."
    elif best.miles_by_level[Risk.SEVERE] > 0:
        warning = "Even the best route has Severe stretches. Drive with extra caution or delay."

    return {
        "departure": departure.isoformat(),
        "load_lb": load_lb,
        "interval_mi": interval_mi,
        "recommended_index": best.index,
        "recommendation_reason": _explain(best, ranked[1] if len(ranked) > 1 else None),
        "warning": warning,
        "routes": [o.as_dict() for o in options],
    }


# --- Heatmap --------------------------------------------------------------------

def corridor_grid(routes: list[list[LonLat]], max_points: int = 180) -> list[LonLat]:
    """Grid points within a buffer of any route.

    Points sit on a fixed global lattice (multiples of `step`), so overlapping
    trips request the same locations and hit the forecast cache.
    """
    all_coords = [c for r in routes for c in r]
    min_x, min_y, max_x, max_y = bbox(all_coords)
    span_mi = haversine_mi((min_x, min_y), (max_x, max_y))
    buffer_mi = min(max(span_mi * 0.08, 25), 80)
    ref = [p for r in routes for p in simplify_for_distance(r, buffer_mi / 3)]

    for step in (0.1, 0.2, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0):
        pad = buffer_mi / 69 + step
        x0, x1 = math.floor((min_x - pad * 1.3) / step), math.ceil((max_x + pad * 1.3) / step)
        y0, y1 = math.floor((min_y - pad) / step), math.ceil((max_y + pad) / step)
        if (x1 - x0) * (y1 - y0) > max_points * 40:
            continue  # bbox far too dense at this step; skip the expensive filter
        pts = [
            (round(i * step, 2), round(j * step, 2))
            for j in range(y0, y1 + 1)
            for i in range(x0, x1 + 1)
            if any(haversine_mi((i * step, j * step), q) <= buffer_mi for q in ref)
        ]
        if len(pts) <= max_points:
            return pts
    raise ValueError("Trip corridor is too large for the heatmap grid")


def hours_of(s: weather.HourlySeries):
    return list(zip(s.wind_mph, s.rain_in, s.snow_in))[: HEATMAP_HOURS + 1]


def heatmap(geometries: list[list[LonLat]], start: datetime, load_lb: float, weather_data: dict | None = None) -> dict:
    points = corridor_grid(geometries)
    forecasts = weather.hourly_forecasts(points, start, HEATMAP_HOURS, weather_data)
    start = weather.floor_hour(start)
    cells = []
    for p in points:
        s = weather.lookup(forecasts, p)
        cells.append({
            "lon": round(p[0], 3),
            "lat": round(p[1], 3),
            "score": [round(risk_score(w, r, sn, load_lb), 2) for w, r, sn in hours_of(s)],
            "wind": [round(w) for w in s.wind_mph[: HEATMAP_HOURS + 1]],
            "rain": [round(r, 2) for r in s.rain_in[: HEATMAP_HOURS + 1]],
            "snow": [round(sn, 2) for sn in s.snow_in[: HEATMAP_HOURS + 1]],
        })
    return {"start": start.isoformat(), "hours": HEATMAP_HOURS, "cells": cells}
