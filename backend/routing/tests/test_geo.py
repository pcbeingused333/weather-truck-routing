import pytest

from routing.geo import cumulative_miles, decode_polyline, haversine_mi, interpolate, sample_route


def test_decode_polyline_precision_6():
    # Start of a real Valhalla shape for a route requested from (41.88, -87.63)
    lon, lat = decode_polyline("q_d{nAbjocfD", 6)[0]
    assert lon == pytest.approx(-87.63, abs=0.001)
    assert lat == pytest.approx(41.88, abs=0.001)


def test_haversine_one_degree_latitude():
    assert haversine_mi((0, 0), (0, 1)) == pytest.approx(69.09, abs=0.05)


def test_interpolate_clamps_and_lerps():
    assert interpolate([0, 10], [0, 100], -5) == 0
    assert interpolate([0, 10], [0, 100], 2.5) == 25
    assert interpolate([0, 10], [0, 100], 50) == 100


def _straight_route(miles: float):
    deg = miles / 69.09
    coords = [(0.0, i * deg / 100) for i in range(101)]
    total = cumulative_miles(coords)[-1]
    # 60 mph everywhere except a slow first 10 miles at 30 mph
    profile = ([0, 10, total], [0, 1200, 1200 + (total - 10) * 60])
    return coords, profile, total


@pytest.mark.parametrize("interval", [10, 25, 50])
def test_samples_every_interval_plus_endpoints(interval):
    coords, profile, total = _straight_route(120)
    samples = sample_route(coords, profile, interval)
    miles = [s.mile for s in samples]
    assert miles[0] == 0
    assert miles[-1] == pytest.approx(total)
    assert all(b - a == pytest.approx(interval) for a, b in zip(miles[:-2], miles[1:-1]))
    assert miles[-1] - miles[-2] <= interval


def test_eta_follows_provider_speed_profile():
    coords, profile, _ = _straight_route(120)
    by_mile = {s.mile: s for s in sample_route(coords, profile, 10)}
    assert by_mile[10].elapsed_s == pytest.approx(1200)  # 10 mi at 30 mph
    assert by_mile[20].elapsed_s == pytest.approx(1800)  # +10 mi at 60 mph


def test_sample_positions_lie_on_route():
    coords, profile, _ = _straight_route(120)
    s = sample_route(coords, profile, 50)[1]
    assert s.lonlat[0] == 0
    assert haversine_mi(coords[0], s.lonlat) == pytest.approx(50, rel=1e-3)
