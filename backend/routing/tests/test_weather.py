from datetime import datetime, timezone

import pytest
from django.core.cache import cache

from routing.providers import http, weather

START = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)
POINTS = [(-111.91, 40.76), (-112.04, 40.81)]  # snap to two different 0.1 deg keys


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


def item(hours: int, rain: float = 0.0) -> dict:
    n = hours + 1
    return {
        "hourly": {
            "time": ["2026-10-22T12:00"],
            "wind_speed_10m": [10.0] * n,
            "wind_gusts_10m": [15.0] * n,
            "rain": [rain] * n,
            "showers": [None] * n,
            "snowfall": [0.0] * n,
        }
    }


def rate_limited(*a, **kw):
    raise http.RateLimited("GET open-meteo returned 429: Daily API request limit exceeded")


def test_rate_limit_asks_the_browser_for_every_missing_point(monkeypatch):
    monkeypatch.setattr(weather, "get_json", rate_limited)
    with pytest.raises(weather.NeedBrowserWeather) as exc:
        weather.hourly_forecasts(POINTS, START, 2)
    req = exc.value.as_request()
    assert [p["key"] for p in req["points"]] == ["-111.9,40.8", "-112.0,40.8"]
    assert req["params"]["start_hour"] == "2026-10-22T12:00" and req["params"]["end_hour"] == "2026-10-22T14:00"


def test_browser_data_is_used_without_calling_open_meteo(monkeypatch):
    monkeypatch.setattr(weather, "get_json", rate_limited)
    supplied = {"-111.9,40.8": item(2, rain=0.3), "-112.0,40.8": item(2)}
    out = weather.hourly_forecasts(POINTS, START, 2, supplied)
    assert out[(-111.9, 40.8)].at(START)["rain_in_hr"] == 0.3
    # Browser data is never cached, so another user's request still goes to Open-Meteo.
    with pytest.raises(weather.NeedBrowserWeather):
        weather.hourly_forecasts(POINTS, START, 2)


def test_incomplete_browser_data_is_a_provider_error_not_another_round_trip(monkeypatch):
    monkeypatch.setattr(weather, "get_json", rate_limited)
    with pytest.raises(http.ProviderError) as exc:
        weather.hourly_forecasts(POINTS, START, 2, {"-111.9,40.8": item(2)})
    assert not isinstance(exc.value, weather.NeedBrowserWeather)


def test_browser_data_for_the_wrong_window_is_rejected(monkeypatch):
    monkeypatch.setattr(weather, "get_json", rate_limited)
    bad = item(2)
    bad["hourly"]["time"] = ["2026-10-22T13:00"]
    with pytest.raises(http.ProviderError):
        weather.hourly_forecasts(POINTS[:1], START, 2, {"-111.9,40.8": bad})


def test_get_json_does_not_retry_a_429(monkeypatch):
    calls = []

    class Resp:
        status_code, ok, text = 429, False, "Daily API request limit exceeded"

    monkeypatch.setattr(http._session, "get", lambda *a, **kw: calls.append(1) or Resp())
    with pytest.raises(http.RateLimited):
        http.get_json("https://example.test", retries=2)
    assert len(calls) == 1
