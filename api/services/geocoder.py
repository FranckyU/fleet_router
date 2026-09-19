import time
from functools import lru_cache
from threading import Lock

import requests
from django.db import transaction
from django.utils import timezone

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "fleet-router/1.0 (student project)"}

_CONNECT_TIMEOUT = 10
_READ_TIMEOUT = 30
_MIN_INTERVAL_S = 1.1           # Nominatim politeness: 1 req/sec
_MAX_ATTEMPTS = 3

_CACHE_STATS = {
    "endpoint_hits": 0,
    "endpoint_misses": 0,
    "station_db_hits": 0,
    "station_db_misses": 0,
    "nominatim_429": 0,
    "nominatim_5xx": 0,
    "nominatim_timeouts": 0,
}

_session = requests.Session()
_session.headers.update(HEADERS)

_rate_lock = Lock()
_last_request_at = 0.0


def _wait_for_rate_limit():
    """Serialize outgoing Nominatim calls at no faster than ~1/sec."""
    global _last_request_at
    with _rate_lock:
        now = time.monotonic()
        gap = now - _last_request_at
        if gap < _MIN_INTERVAL_S:
            time.sleep(_MIN_INTERVAL_S - gap)
        _last_request_at = time.monotonic()


def _nominatim_get(location: str):
    """Perform a Nominatim request with retries on throttle/timeout."""
    last_exc = None

    for attempt in range(_MAX_ATTEMPTS):
        try:
            _wait_for_rate_limit()
            r = _session.get(
                NOMINATIM_URL,
                params={
                    "q": location,
                    "format": "json",
                    "limit": 1,
                    "countrycodes": "us",
                },
                timeout=(_CONNECT_TIMEOUT, _READ_TIMEOUT),
            )

            if r.status_code == 429:
                _CACHE_STATS["nominatim_429"] += 1
                last_exc = RuntimeError("Nominatim: rate limit (429)")
                time.sleep(2 ** attempt)
                continue

            if 500 <= r.status_code < 600:
                _CACHE_STATS["nominatim_5xx"] += 1
                last_exc = RuntimeError(f"Nominatim: HTTP {r.status_code}")
                time.sleep(2 ** attempt)
                continue

            r.raise_for_status()
            data = r.json()
            if not data:
                raise ValueError(f"Could not geocode: {location}")
            return float(data[0]["lat"]), float(data[0]["lon"])

        except (requests.ReadTimeout, requests.ConnectTimeout) as e:
            _CACHE_STATS["nominatim_timeouts"] += 1
            last_exc = e
            time.sleep(2 ** attempt)

        except requests.ConnectionError as e:
            last_exc = e
            time.sleep(2 ** attempt)

    raise last_exc if last_exc is not None else RuntimeError("Nominatim failed")


@lru_cache(maxsize=1024)
def _geocode_nominatim(location: str):
    """The ONLY place Nominatim is called. Cached per unique string."""
    _CACHE_STATS["endpoint_misses"] += 1
    return _nominatim_get(location)


def geocode_address(location: str):
    """Geocode a user-supplied city string. lru_cached."""
    key = location.strip()
    info = _geocode_nominatim.cache_info()
    result = _geocode_nominatim(key)
    if _geocode_nominatim.cache_info().hits > info.hits:
        _CACHE_STATS["endpoint_hits"] += 1
    return result


def geocode_station(station):
    """
    Lazily geocode a FuelStation row and persist to DB. Idempotent.

    - Fast path: already geocoded → return from memory, zero DB/network.
    - Slow path: acquire a row lock, re-check, then hit Nominatim once.
      Two workers racing on the same station issue exactly one request.
    """
    if station.is_geocoded:
        _CACHE_STATS["station_db_hits"] += 1
        return station.latitude, station.longitude

    _CACHE_STATS["station_db_misses"] += 1

    with transaction.atomic():
        locked = (
            type(station)
            .objects
            .select_for_update()
            .get(pk=station.pk)
        )

        if locked.is_geocoded:
            station.latitude    = locked.latitude
            station.longitude   = locked.longitude
            station.geocoded_at = locked.geocoded_at
            return locked.latitude, locked.longitude

        lat, lon = geocode_address(f"{locked.city}, {locked.state}")
        locked.latitude    = lat
        locked.longitude   = lon
        locked.geocoded_at = timezone.now()
        locked.save(update_fields=["latitude", "longitude", "geocoded_at"])

    station.latitude    = lat
    station.longitude   = lon
    station.geocoded_at = locked.geocoded_at
    return lat, lon
