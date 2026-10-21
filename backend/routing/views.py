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
    return Response({"ok": True})
