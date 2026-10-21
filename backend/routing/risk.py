"""Weather risk classification for a single checkpoint.

Pure functions only: no I/O, so every rule in the assessment brief is unit tested.

Band boundaries (the brief writes ranges like "25-34" and "0.10-0.25" that share
endpoints, so we fix the convention explicitly):

* Wind (mph, whole numbers in the brief): Low <25, Moderate 25-<35, High 35-<45,
  Severe 45-<55, No Travel >=55.
* Rain / snow (in/hr): a value on a shared boundary goes to the *higher* band,
  except the top one, which the brief defines as strictly greater (>1.00 rain,
  >3.0 snow). So rain 0.25 is High, 1.00 is Severe, 1.01 is No Travel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class Risk(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return self.name.replace("_", " ").title()


# (lower bound of Moderate, High, Severe, No Travel)
WIND_BANDS_MPH = (25, 35, 45, 55)
RAIN_BANDS_IN_HR = (0.10, 0.25, 0.50)
RAIN_NO_TRAVEL_ABOVE = 1.00
SNOW_BANDS_IN_HR = (0.5, 1.0, 2.0)
SNOW_NO_TRAVEL_ABOVE = 3.0

HEAVY_LOAD_LB = 40_000  # 35-44 mph wind + load above this -> Severe
VERY_HEAVY_LOAD_LB = 30_000  # 45-54 mph wind + load above this -> No Travel


def _band(value: float, lower_bounds: tuple[float, ...]) -> Risk:
    level = Risk.LOW
    for i, bound in enumerate(lower_bounds, start=1):
        if value >= bound:
            level = Risk(i)
    return level


def wind_risk(mph: float) -> Risk:
    return _band(mph, WIND_BANDS_MPH)


def rain_risk(in_hr: float) -> Risk:
    if in_hr > RAIN_NO_TRAVEL_ABOVE:
        return Risk.NO_TRAVEL
    return _band(in_hr, RAIN_BANDS_IN_HR)


def snow_risk(in_hr: float) -> Risk:
    if in_hr > SNOW_NO_TRAVEL_ABOVE:
        return Risk.NO_TRAVEL
    return _band(in_hr, SNOW_BANDS_IN_HR)


def load_adjusted_wind_risk(mph: float, load_lb: float) -> tuple[Risk, str | None]:
    """Apply the load rules on top of the wind band. Returns (risk, reason)."""
    base = wind_risk(mph)
    if base == Risk.SEVERE and load_lb > VERY_HEAVY_LOAD_LB:
        return Risk.NO_TRAVEL, f"45–54 mph wind with load >{VERY_HEAVY_LOAD_LB:,} lb"
    if base == Risk.HIGH and load_lb > HEAVY_LOAD_LB:
        return Risk.SEVERE, f"35–44 mph wind with load >{HEAVY_LOAD_LB:,} lb"
    return base, None


@dataclass(frozen=True)
class Assessment:
    level: Risk
    wind: Risk
    rain: Risk
    snow: Risk
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "level": int(self.level),
            "label": self.level.label,
            "wind": int(self.wind),
            "rain": int(self.rain),
            "snow": int(self.snow),
            "reasons": self.reasons,
        }


def assess(wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float) -> Assessment:
    """Overall checkpoint risk is the worst of the three conditions after load rules."""
    wind, load_reason = load_adjusted_wind_risk(wind_mph, load_lb)
    rain = rain_risk(rain_in_hr)
    snow = snow_risk(snow_in_hr)
    level = max(wind, rain, snow)

    reasons: list[str] = []
    if level > Risk.LOW:
        if wind == level:
            reasons.append(load_reason or f"Wind {wind_mph:.0f} mph")
        if rain == level:
            reasons.append(f"Rain {rain_in_hr:.2f} in/hr")
        if snow == level:
            reasons.append(f"Snow {snow_in_hr:.2f} in/hr")
    return Assessment(level=level, wind=wind, rain=rain, snow=snow, reasons=reasons)


def risk_score(wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float) -> float:
    """Continuous 0-4 score for the heatmap: the band index plus how far into the band.

    Discrete levels make a blocky heatmap; this keeps the same ordering as `assess`
    (floor(score) == level) while varying smoothly inside each band.
    """

    def frac(value: float, edges: tuple[float, ...]) -> float:
        # edges: 0, then the lower bounds of each band, then a cap for No Travel
        for i in range(len(edges) - 1):
            lo, hi = edges[i], edges[i + 1]
            if value < hi:
                return i + (value - lo) / (hi - lo)
        return 4.0

    level = int(assess(wind_mph, rain_in_hr, snow_in_hr, load_lb).level)
    if level == Risk.NO_TRAVEL:
        return 4.0
    parts = [
        frac(wind_mph, (0, *WIND_BANDS_MPH)),
        frac(rain_in_hr, (0, *RAIN_BANDS_IN_HR, RAIN_NO_TRAVEL_ABOVE)),
        frac(snow_in_hr, (0, *SNOW_BANDS_IN_HR, SNOW_NO_TRAVEL_ABOVE)),
    ]
    # Never let the in-band fraction cross into the next level (load rules can
    # raise the level above the raw wind band, so clamp to [level, level+1)).
    return min(max(max(parts), level), level + 0.999)
