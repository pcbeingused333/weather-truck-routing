"""Hourly forecasts from Open-Meteo (no API key, many locations per request)."""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.core.cache import cache

from ..geo import LonLat
from .http import ProviderError, get_json

HOURLY_VARS = ("wind_speed_10m", "wind_gusts_10m", "rain", "showers", "snowfall")
LOCATIONS_PER_REQUEST = 50
CACHE_SECONDS = 15 * 60


class OutsideForecastWindow(Exception):
    """A requested time is outside the forecast data we have (a user input problem)."""


@dataclass
class HourlySeries:
    """Hourly values for one location, starting at `start` (UTC, on the hour)."""

    start: datetime
    wind_mph: list[float]
    gust_mph: list[float]
    rain_in: list[float]  # liquid precipitation (rain + showers) per hour
    snow_in: list[float]  # snowfall depth per hour

    def at(self, when: datetime) -> dict:
        """Values at `when`, linearly interpolated between the surrounding hours."""
        h = (when - self.start).total_seconds() / 3600
        if h < 0 or h > len(self.wind_mph) - 1:
            raise OutsideForecastWindow(f"{when.isoformat()} is outside the forecast window")
        i = min(int(h), len(self.wind_mph) - 2)
        t = h - i

        def lerp(series: list[float]) -> float:
            return series[i] + t * (series[i + 1] - series[i])

        # Wind is an instantaneous value, so interpolate. Rain and snow are totals
        # for the hour *ending* at each timestamp, so take the bucket covering `when`.
        bucket = min(math.ceil(h), len(self.rain_in) - 1)
        return {
            "wind_mph": lerp(self.wind_mph),
            "gust_mph": lerp(self.gust_mph),
            "rain_in_hr": self.rain_in[bucket],
            "snow_in_hr": self.snow_in[bucket],
        }


def floor_hour(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def _key(lonlat: LonLat) -> tuple[float, float]:
    # Snap to 0.1 deg (~7 mi), on the order of the forecast models' own grid
    # spacing. Open-Meteo bills every location as one call, so this lets the
    # three routes (which share most of their corridor) share forecasts.
    return round(lonlat[0], 1), round(lonlat[1], 1)


def _fetch_chunk(points: list[tuple[float, float]], start: datetime, end: datetime) -> list[HourlySeries]:
    data = get_json(
        settings.OPEN_METEO_URL,
        timeout=40,
        retries=1,
        params={
            "latitude": ",".join(str(p[1]) for p in points),
            "longitude": ",".join(str(p[0]) for p in points),
            "hourly": ",".join(HOURLY_VARS),
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timezone": "GMT",
            "start_hour": start.strftime("%Y-%m-%dT%H:%M"),
            "end_hour": end.strftime("%Y-%m-%dT%H:%M"),
        },
    )
    items = data if isinstance(data, list) else [data]
    if len(items) != len(points):
        raise ProviderError("Open-Meteo returned an unexpected number of locations")
    out = []
    expected_first = start.strftime("%Y-%m-%dT%H:%M")
    for item in items:
        h = item["hourly"]
        if not h["time"] or h["time"][0] != expected_first:
            raise ProviderError("Open-Meteo returned a different time window than requested")
        zero = lambda xs: [x or 0.0 for x in xs]  # noqa: E731 - nulls mean "no data", treat as calm
        out.append(
            HourlySeries(
                start=start,
                wind_mph=zero(h["wind_speed_10m"]),
                gust_mph=zero(h["wind_gusts_10m"]),
                rain_in=[a + b for a, b in zip(zero(h["rain"]), zero(h["showers"]))],
                snow_in=zero(h["snowfall"]),
            )
        )
    return out


def hourly_forecasts(points: list[LonLat], start: datetime, hours: int) -> dict[tuple[float, float], HourlySeries]:
    """Forecasts covering [start, start + hours] for each point, keyed by rounded lon/lat."""
    start = floor_hour(start)
    end = start + timedelta(hours=hours)
    keys = list(dict.fromkeys(_key(p) for p in points))

    result: dict[tuple[float, float], HourlySeries] = {}
    missing = []
    for k in keys:
        hit = cache.get(f"wx:{k[0]}_{k[1]}:{start:%Y%m%d%H}:{hours}")
        if hit is not None:
            result[k] = hit
        else:
            missing.append(k)

    chunks = [missing[i : i + LOCATIONS_PER_REQUEST] for i in range(0, len(missing), LOCATIONS_PER_REQUEST)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for chunk, series in zip(chunks, pool.map(lambda c: _fetch_chunk(c, start, end), chunks)):
            for k, s in zip(chunk, series):
                result[k] = s
                cache.set(f"wx:{k[0]}_{k[1]}:{start:%Y%m%d%H}:{hours}", s, CACHE_SECONDS)
    return result


def lookup(forecasts: dict, lonlat: LonLat) -> HourlySeries:
    return forecasts[_key(lonlat)]
