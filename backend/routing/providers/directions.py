"""Route alternatives from Valhalla (truck costing), with OSRM as a fallback.

Public routers rarely return three distinct alternatives for every trip, so when
they come up short we ask for detours through a via point offset to either side
of the straight line between origin and destination, and keep only candidates
that differ meaningfully from the routes we already have.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache

from ..geo import LonLat, decode_polyline, haversine_mi, simplify_for_distance
from .http import ProviderError, get_json, post_json

log = logging.getLogger(__name__)

METERS_PER_MILE = 1609.344
EMPTY_TRACTOR_TRAILER_LB = 35_000
LB_PER_METRIC_TON = 2204.62

WANTED_ROUTES = 3
DETOUR_OFFSETS = (0.15, -0.15, 0.3, -0.3)  # fraction of the straight-line distance
MAX_OVERLAP = 0.85  # a candidate sharing more than this with a kept route is a duplicate


@dataclass
class Route:
    coords: list[LonLat]
    distance_mi: float
    duration_s: float
    # (cumulative miles, cumulative seconds) at provider-reported breakpoints
    time_profile: tuple[list[float], list[float]]
    source: str
    via: LonLat | None = None


# --- Valhalla -------------------------------------------------------------------

def _valhalla_payload(origin: LonLat, dest: LonLat, load_lb: float, alternates: int) -> dict:
    gross_tons = (EMPTY_TRACTOR_TRAILER_LB + load_lb) / LB_PER_METRIC_TON
    return {
        "locations": [{"lon": origin[0], "lat": origin[1]}, {"lon": dest[0], "lat": dest[1]}],
        "costing": "truck",
        "costing_options": {"truck": {"weight": round(gross_tons, 1)}},
        "units": "miles",
        "alternates": alternates,
        "directions_type": "maneuvers",
    }


def _parse_valhalla_trip(trip: dict) -> Route:
    coords: list[LonLat] = []
    miles, secs = [0.0], [0.0]
    for leg in trip["legs"]:
        leg_coords = decode_polyline(leg["shape"], 6)
        coords.extend(leg_coords if not coords else leg_coords[1:])
        for m in leg["maneuvers"]:
            miles.append(miles[-1] + m["length"])
            secs.append(secs[-1] + m["time"])
    return Route(
        coords=coords,
        distance_mi=trip["summary"]["length"],
        duration_s=trip["summary"]["time"],
        time_profile=(miles, secs),
        source="valhalla",
    )


def valhalla_routes(origin: LonLat, dest: LonLat, load_lb: float, alternates: int = 2) -> list[Route]:
    data = post_json(f"{settings.VALHALLA_URL}/route", _valhalla_payload(origin, dest, load_lb, alternates))
    trips = [data["trip"], *(alt["trip"] for alt in data.get("alternates", []))]
    return [_parse_valhalla_trip(t) for t in trips]


def join(first: Route, second: Route) -> Route:
    """Concatenate two consecutive legs (first ends where second starts)."""
    miles, secs = first.time_profile
    m2, s2 = second.time_profile
    return Route(
        coords=first.coords + second.coords[1:],
        distance_mi=first.distance_mi + second.distance_mi,
        duration_s=first.duration_s + second.duration_s,
        time_profile=(miles + [miles[-1] + m for m in m2[1:]], secs + [secs[-1] + s for s in s2[1:]]),
        source=first.source,
    )


# --- OSRM -----------------------------------------------------------------------

def osrm_routes(locations: list[LonLat], alternates: int = 2) -> list[Route]:
    path = ";".join(f"{lon},{lat}" for lon, lat in locations)
    data = get_json(
        f"{settings.OSRM_URL}/route/v1/driving/{path}",
        params={
            "alternatives": str(alternates) if alternates else "false",
            "overview": "full",
            "geometries": "geojson",
            "annotations": "distance,duration",
        },
    )
    if data.get("code") != "Ok":
        raise ProviderError(f"OSRM: {data.get('message', data.get('code'))}")
    routes = []
    for r in data["routes"]:
        miles, secs = [0.0], [0.0]
        for leg in r["legs"]:
            ann = leg["annotation"]
            for d, t in zip(ann["distance"], ann["duration"]):
                miles.append(miles[-1] + d / METERS_PER_MILE)
                secs.append(secs[-1] + t)
        routes.append(
            Route(
                coords=[tuple(c) for c in r["geometry"]["coordinates"]],
                distance_mi=r["distance"] / METERS_PER_MILE,
                duration_s=r["duration"],
                time_profile=(miles, secs),
                source="osrm",
            )
        )
    return routes


# --- Alternatives ---------------------------------------------------------------

def _overlap(candidate: Route, other: Route, tolerance_mi: float = 1.5) -> float:
    """Share of the candidate's length that lies within `tolerance_mi` of `other`."""
    cand = simplify_for_distance(candidate.coords, 5)
    ref = simplify_for_distance(other.coords, 1)
    near = sum(1 for p in cand if any(haversine_mi(p, q) <= tolerance_mi for q in ref))
    return near / len(cand)


def _is_distinct(candidate: Route, kept: list[Route]) -> bool:
    return all(_overlap(candidate, r) < MAX_OVERLAP for r in kept)


def _detour_point(origin: LonLat, dest: LonLat, offset_frac: float) -> LonLat:
    """A point off the midpoint, perpendicular to the origin->destination line."""
    mid_lat = math.radians((origin[1] + dest[1]) / 2)
    # Work in a local equirectangular frame (x scaled by cos(lat)).
    dx = (dest[0] - origin[0]) * math.cos(mid_lat)
    dy = dest[1] - origin[1]
    length = math.hypot(dx, dy) or 1.0
    px, py = -dy / length, dx / length
    dist = length * offset_frac
    return (
        (origin[0] + dest[0]) / 2 + px * dist / math.cos(mid_lat),
        (origin[1] + dest[1]) / 2 + py * dist,
    )


def get_alternatives(origin: LonLat, dest: LonLat, load_lb: float) -> list[Route]:
    # Re-planning the same trip (e.g. a different sampling interval or departure)
    # shouldn't hit the routers again. Truck weight only matters in coarse steps.
    key = "routes:{:.4f},{:.4f}:{:.4f},{:.4f}:{}".format(*origin, *dest, round(load_lb, -3))
    if (hit := cache.get(key)) is not None:
        return hit
    routes = _find_alternatives(origin, dest, load_lb)
    cache.set(key, routes, 60 * 60)
    return routes


def _find_alternatives(origin: LonLat, dest: LonLat, load_lb: float) -> list[Route]:
    try:
        candidates = valhalla_routes(origin, dest, load_lb, alternates=2)
    except ProviderError as exc:
        log.warning("Valhalla failed (%s); falling back to OSRM", exc)
        candidates = osrm_routes([origin, dest], alternates=2)
    if not candidates:
        raise ProviderError("No route found between these points")
    source = candidates[0].source

    def detour_via(via: LonLat) -> Route:
        # Two separate legs instead of one request with a via point: Valhalla's
        # public server caps multi-point requests at 1500 km, and this keeps the
        # detour on the same provider (and truck speeds) as the main route.
        if source == "valhalla":
            return join(valhalla_routes(origin, via, load_lb, 0)[0], valhalla_routes(via, dest, load_lb, 0)[0])
        return osrm_routes([origin, via, dest], alternates=0)[0]

    kept: list[Route] = []
    for r in candidates:
        if _is_distinct(r, kept):
            kept.append(r)

    for offset in DETOUR_OFFSETS:
        if len(kept) >= WANTED_ROUTES:
            break
        via = _detour_point(origin, dest, offset)
        try:
            detour = detour_via(via)
        except ProviderError as exc:
            log.info("Detour via %s failed: %s", via, exc)
            continue
        # Reject absurd detours (e.g. a via point that forced a ferry or a loop).
        if detour.distance_mi > kept[0].distance_mi * 1.6:
            continue
        if _is_distinct(detour, kept):
            detour.via = via
            kept.append(detour)

    return kept[:WANTED_ROUTES]
