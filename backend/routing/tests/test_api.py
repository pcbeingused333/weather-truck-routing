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


def test_rate_limited_weather_asks_the_browser_and_accepts_its_data(monkeypatch):
    from datetime import datetime, timezone

    from routing.providers.weather import NeedBrowserWeather

    start = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)
    seen = {}

    def plan_routes(**kw):
        seen.update(kw)
        if kw["weather_data"] is None:
            raise NeedBrowserWeather([(-111.9, 40.8)], start, start)
        return {"routes": []}

    monkeypatch.setattr(planner, "plan_routes", plan_routes)
    r = APIClient().post("/api/plan", body(), format="json")
    assert r.status_code == 503
    req = r.json()["weather_request"]
    assert r.json()["code"] == "weather_from_browser"
    assert req["points"] == [{"key": "-111.9,40.8", "lon": -111.9, "lat": 40.8}]
    assert req["params"]["start_hour"] == "2026-10-22T12:00" and "rain" in req["params"]["hourly"]

    supplied = {"-111.9,40.8": {"hourly": {"time": ["2026-10-22T12:00"], "rain": [0]}}}
    r = APIClient().post("/api/plan", body(weather=supplied), format="json")
    assert r.status_code == 200
    assert seen["weather_data"] == supplied


def test_browser_weather_is_capped(monkeypatch):
    monkeypatch.setattr(planner, "plan_routes", lambda **kw: {"routes": []})
    too_many = {f"{i},{i}": {} for i in range(601)}
    r = APIClient().post("/api/plan", body(weather=too_many), format="json")
    assert r.status_code == 400 and "weather" in r.json()
