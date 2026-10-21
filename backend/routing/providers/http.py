import time

import requests
from django.conf import settings

_session = requests.Session()
_session.headers["User-Agent"] = settings.HTTP_USER_AGENT


class ProviderError(Exception):
    """An upstream API failed or returned something unusable."""


def get_json(url: str, *, params=None, timeout: float = 20, retries: int = 0):
    for attempt in range(retries + 1):
        try:
            resp = _session.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            if attempt == retries:
                raise ProviderError(f"GET {url} failed: {exc}") from exc
            time.sleep(1.5 * (attempt + 1))


def post_json(url: str, payload: dict, *, timeout: float = 30):
    try:
        resp = _session.post(url, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise ProviderError(f"POST {url} failed: {exc}") from exc
    if not resp.ok:
        raise ProviderError(f"POST {url} returned {resp.status_code}: {resp.text[:200]}")
    try:
        return resp.json()
    except ValueError as exc:
        raise ProviderError(f"POST {url} returned invalid JSON") from exc
