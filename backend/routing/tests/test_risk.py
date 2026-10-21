import pytest

from routing.risk import Risk, assess, rain_risk, risk_score, snow_risk, wind_risk


@pytest.mark.parametrize("mph,expected", [
    (0, Risk.LOW), (24.9, Risk.LOW),
    (25, Risk.MODERATE), (34.9, Risk.MODERATE),
    (35, Risk.HIGH), (44.9, Risk.HIGH),
    (45, Risk.SEVERE), (54.9, Risk.SEVERE),
    (55, Risk.NO_TRAVEL), (80, Risk.NO_TRAVEL),
])
def test_wind_bands(mph, expected):
    assert wind_risk(mph) == expected


@pytest.mark.parametrize("inches,expected", [
    (0, Risk.LOW), (0.09, Risk.LOW),
    (0.10, Risk.MODERATE), (0.24, Risk.MODERATE),
    (0.25, Risk.HIGH), (0.49, Risk.HIGH),
    (0.50, Risk.SEVERE), (1.00, Risk.SEVERE),
    (1.01, Risk.NO_TRAVEL),
])
def test_rain_bands(inches, expected):
    assert rain_risk(inches) == expected


@pytest.mark.parametrize("inches,expected", [
    (0.4, Risk.LOW), (0.5, Risk.MODERATE), (1.0, Risk.HIGH),
    (2.0, Risk.SEVERE), (3.0, Risk.SEVERE), (3.1, Risk.NO_TRAVEL),
])
def test_snow_bands(inches, expected):
    assert snow_risk(inches) == expected


def test_55_mph_is_no_travel_for_any_load():
    assert assess(55, 0, 0, load_lb=0).level == Risk.NO_TRAVEL


@pytest.mark.parametrize("load,expected", [(30_000, Risk.SEVERE), (30_001, Risk.NO_TRAVEL)])
def test_45_to_54_mph_with_load_over_30k_is_no_travel(load, expected):
    a = assess(50, 0, 0, load)
    assert a.level == expected
    if expected == Risk.NO_TRAVEL:
        assert "30,000" in a.reasons[0]


@pytest.mark.parametrize("load,expected", [(40_000, Risk.HIGH), (40_001, Risk.SEVERE)])
def test_35_to_44_mph_with_load_over_40k_is_severe(load, expected):
    assert assess(40, 0, 0, load).level == expected


def test_load_rules_do_not_touch_low_wind():
    assert assess(20, 0, 0, 80_000).level == Risk.LOW


def test_overall_level_is_worst_condition_and_names_it():
    a = assess(wind_mph=10, rain_in_hr=0.3, snow_in_hr=0.6, load_lb=10_000)
    assert a.level == Risk.HIGH
    assert a.reasons == ["Rain 0.30 in/hr"]


def test_low_has_no_reasons():
    assert assess(5, 0, 0, 10_000).reasons == []


@pytest.mark.parametrize("args", [(0, 0, 0), (30, 0, 0), (40, 0.3, 0), (50, 0, 2.5), (20, 0.6, 0), (70, 0, 0)])
@pytest.mark.parametrize("load", [10_000, 45_000])
def test_score_floor_matches_level(args, load):
    assert int(risk_score(*args, load)) == int(assess(*args, load).level)


def test_score_increases_within_band():
    assert risk_score(26, 0, 0, 0) < risk_score(33, 0, 0, 0)
