from datetime import datetime, timedelta, timezone

import pytest

from routing import planner
from routing.providers import directions, weather
from routing.risk import Risk

DEPART = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)


def straight(lon: float, miles: float = 100, mph: float = 50) -> directions.Route:
    deg = miles / 69.09
    coords = [(lon, i * deg / 50) for i in range(51)]
    return directions.Route(coords, miles, miles / mph * 3600, ([0, miles], [0, miles / mph * 3600]), "test")


def fake_forecasts(wind_by_lon: dict[float, float]):
    def _fetch(points, start, hours, supplied=None):
        out = {}
        for p in points:
            k = weather._key(p)
            wind = wind_by_lon.get(round(p[0], 1), 0)
            n = hours + 1
            out[k] = weather.HourlySeries(weather.floor_hour(start), [wind] * n, [wind] * n, [0.0] * n, [0.0] * n)
        return out
    return _fetch


@pytest.fixture
def plan(monkeypatch):
    def run(routes, wind_by_lon, load=20_000, interval=25):
        monkeypatch.setattr(directions, "get_alternatives", lambda *a: routes)
        monkeypatch.setattr(weather, "hourly_forecasts", fake_forecasts(wind_by_lon))
        return planner.plan_routes((0, 0), (0, 1.5), DEPART, load, interval)
    return run


def test_prefers_fewer_severe_miles_over_speed(plan):
    fast_but_windy, slow_but_calm = straight(0.0, mph=65), straight(1.0, mph=40)
    result = plan([fast_but_windy, slow_but_calm], {0.0: 48})
    assert result["recommended_index"] == 1
    assert result["routes"][0]["miles_by_level"]["Severe"] == 100
    assert "Severe" in result["recommendation_reason"]


def test_load_rule_turns_severe_into_no_travel(plan):
    result = plan([straight(0.0)], {0.0: 48}, load=35_000)
    assert result["routes"][0]["miles_by_level"]["No Travel"] == 100
    assert "delaying" in result["warning"]


def test_high_miles_break_ties_on_severe(plan):
    result = plan([straight(0.0, mph=65), straight(1.0, mph=40)], {0.0: 38})
    assert result["recommended_index"] == 1
    assert "High" in result["recommendation_reason"]


def test_equal_weather_picks_fastest(plan):
    result = plan([straight(0.0, mph=40), straight(1.0, mph=60)], {})
    assert result["recommended_index"] == 1
    assert "faster" in result["recommendation_reason"]
    assert [r["rank"] for r in result["routes"]] == [2, 1]


def test_checkpoint_eta_uses_departure_plus_elapsed(plan):
    result = plan([straight(0.0, miles=100, mph=50)], {}, interval=50)
    etas = [cp["eta"] for cp in result["routes"][0]["checkpoints"]]
    assert etas == [(DEPART + timedelta(hours=h)).isoformat() for h in (0, 1, 2)]


def test_segment_takes_worse_endpoint(plan):
    # Wind only at lon 0.0; a route that starts there and drifts east
    r = straight(0.0)
    r.coords = [(0.0 + i * 0.01, y) for i, (_, y) in enumerate(r.coords)]  # ends at lon 0.5
    result = plan([r], {0.0: 40}, interval=25)
    levels = [cp["risk"]["level"] for cp in result["routes"][0]["checkpoints"]]
    assert levels[0] == Risk.HIGH and levels[1] == Risk.LOW
    assert result["routes"][0]["miles_by_level"]["High"] == 25


def test_heatmap_hourly_arrays(monkeypatch):
    monkeypatch.setattr(weather, "hourly_forecasts", fake_forecasts({}))
    out = planner.heatmap([straight(0.0).coords], DEPART, 20_000)
    assert out["cells"]
    assert all(len(c["score"]) == planner.HEATMAP_HOURS + 1 for c in out["cells"])


def test_lower_average_risk_beats_slightly_faster_route(plan):
    # Both routes only Low/Moderate; B is a bit slower but less exposed.
    a = straight(0.0, mph=60)
    b = straight(1.0, mph=58)
    a.coords = [(0.0 + i * 0.004, y) for i, (_, y) in enumerate(a.coords)]  # drifts into lon 0.1 wind
    result = plan([a, b], {0.0: 30, 0.1: 30, 1.0: 0})
    assert result["routes"][0]["avg_risk"] > result["routes"][1]["avg_risk"] > -1
    assert result["recommended_index"] == 1
    assert "average risk" in result["recommendation_reason"]


def test_precipitation_uses_bucket_for_the_hour_containing_eta():
    s = weather.HourlySeries(DEPART, [0.0, 0.0, 0.0], [0.0] * 3, [0.0, 0.6, 0.0], [0.0, 0.0, 2.5])
    # 12:30 falls in the hour ending 13:00 (index 1): its rain total, not a blend.
    assert s.at(DEPART + timedelta(minutes=30))["rain_in_hr"] == 0.6
    assert s.at(DEPART + timedelta(minutes=90))["snow_in_hr"] == 2.5


def test_eta_outside_forecast_raises_input_error():
    s = weather.HourlySeries(DEPART, [0.0] * 3, [0.0] * 3, [0.0] * 3, [0.0] * 3)
    with pytest.raises(weather.OutsideForecastWindow):
        s.at(DEPART + timedelta(hours=5))
