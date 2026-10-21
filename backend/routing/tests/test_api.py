from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APIClient

from routing import planner


def body(**over):
    b = {
        "origin": {"lat": 41.88, "lon": -87.63},
        "destination": {"lat": 39.74, "lon": -104.99},
        "departure": (timezone.now() + timedelta(hours=1)).isoformat(),
        "load_lb": 30000,
        "interval_mi": 25,
    }
    b.update(over)
    return b


def test_plan_rejects_bad_interval_and_past_departure():
    r = APIClient().post("/api/plan", body(interval_mi=30, departure="2020-01-01T00:00:00Z"), format="json")
    assert r.status_code == 400
    assert set(r.json()) == {"interval_mi", "departure"}


def test_plan_rejects_same_origin_and_destination():
    r = APIClient().post("/api/plan", body(destination={"lat": 41.88, "lon": -87.63}), format="json")
    assert r.status_code == 400


def test_plan_calls_planner(monkeypatch):
    seen = {}
    monkeypatch.setattr(planner, "plan_routes", lambda **kw: seen.update(kw) or {"routes": []})
    r = APIClient().post("/api/plan", body(), format="json")
    assert r.status_code == 200
    assert seen["origin"] == (-87.63, 41.88) and seen["interval_mi"] == 25


def test_provider_failure_is_502(monkeypatch):
    from routing.providers.http import ProviderError

    def boom(**kw):
        raise ProviderError("down")

    monkeypatch.setattr(planner, "plan_routes", boom)
    assert APIClient().post("/api/plan", body(), format="json").status_code == 502


def test_outside_forecast_is_400_not_502(monkeypatch):
    from routing.providers.weather import OutsideForecastWindow

    def boom(**kw):
        raise OutsideForecastWindow("late")

    monkeypatch.setattr(planner, "plan_routes", boom)
    assert APIClient().post("/api/plan", body(), format="json").status_code == 400
