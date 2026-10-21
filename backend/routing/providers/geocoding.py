"""Place search via Nominatim (OpenStreetMap). No API key; results are cached."""

from django.conf import settings
from django.core.cache import cache

from .http import ProviderError, get_json


def search(query: str, limit: int = 5) -> list[dict]:
    key = f"geocode:{query.lower().strip()}:{limit}"
    if (hit := cache.get(key)) is not None:
        return hit
    data = get_json(
        f"{settings.NOMINATIM_URL}/search",
        params={"q": query, "format": "jsonv2", "limit": limit, "countrycodes": "us,ca,mx"},
    )
    if not isinstance(data, list):
        raise ProviderError("Unexpected geocoder response")
    results = [{"label": d["display_name"], "lat": float(d["lat"]), "lon": float(d["lon"])} for d in data]
    cache.set(key, results, 60 * 60 * 24)
    return results
