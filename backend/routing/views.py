import logging

from rest_framework import status
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from . import planner
from .providers import geocoding
from .providers.http import ProviderError
from .serializers import HeatmapRequestSerializer, PlanRequestSerializer

log = logging.getLogger(__name__)


def _upstream_error(exc: ProviderError) -> Response:
    log.warning("Upstream provider error: %s", exc)
    return Response(
        {"detail": "A routing or weather provider is unavailable right now. Please try again."},
        status=status.HTTP_502_BAD_GATEWAY,
    )


@api_view(["GET"])
def geocode(request):
    q = request.query_params.get("q", "").strip()
    if len(q) < 3:
        return Response([])
    try:
        return Response(geocoding.search(q))
    except ProviderError as exc:
        return _upstream_error(exc)


@api_view(["POST"])
@throttle_classes([AnonRateThrottle])
def plan(request):
    s = PlanRequestSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    d = s.validated_data
    try:
        result = planner.plan_routes(
            origin=(d["origin"]["lon"], d["origin"]["lat"]),
            dest=(d["destination"]["lon"], d["destination"]["lat"]),
            departure=d["departure"],
            load_lb=d["load_lb"],
            interval_mi=d["interval_mi"],
        )
    except ProviderError as exc:
        return _upstream_error(exc)
    return Response(result)


@api_view(["POST"])
@throttle_classes([AnonRateThrottle])
def heatmap(request):
    s = HeatmapRequestSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    d = s.validated_data
    try:
        geometries = [[(p[0], p[1]) for p in r] for r in d["routes"]]
        return Response(planner.heatmap(geometries, d["start"], d["load_lb"]))
    except ProviderError as exc:
        return _upstream_error(exc)


@api_view(["GET"])
def health(request):
    """`?deep=1` also probes each upstream provider (used to diagnose 502s)."""
    if request.query_params.get("deep") != "1":
        return Response({"ok": True})
    return Response({"ok": True, "providers": providers_status()})


def providers_status() -> dict:
    from datetime import datetime, timezone

    from .providers import directions, weather

    a, b = (-87.63, 41.88), (-88.0, 41.8)
    checks = {
        "valhalla": lambda: directions.valhalla_routes(a, b, 20_000, 0),
        "osrm": lambda: directions.osrm_routes([a, b], 0),
        "open_meteo": lambda: weather._fetch_chunk([a], weather.floor_hour(datetime.now(timezone.utc)), weather.floor_hour(datetime.now(timezone.utc))),
        "nominatim": lambda: geocoding.search("Chicago", 1),
    }
    out = {}
    for name, check in checks.items():
        try:
            check()
            out[name] = "ok"
        except ProviderError as exc:
            out[name] = str(exc)[:300]
    return out
