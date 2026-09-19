import re
import time
from threading import Lock

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

OSRM_BASE = "https://router.project-osrm.org/route/v1/driving"

# OSRM demo server fair-use policy: max 1 request per second.
# https://github.com/Project-OSRM/osrm-backend/wiki/Demo-server
HEADERS = {"User-Agent": "fleet-router/1.0 (student project)"}

_MIN_INTERVAL_S = 1.0            # 1 req/sec, per the demo server policy
_MAX_ATTEMPTS   = 3

_CONNECT_TIMEOUT = 5
_HIGHWAYS_READ_TIMEOUT = 30
_ROUTE_READ_TIMEOUT = 60

# Module-level rate limiter shared across all threads in this process.
_rate_lock = Lock()
_last_request_at = 0.0

# Shared session: connection reuse + retry on transient 5xx/429.
_session = requests.Session()
_session.headers.update(HEADERS)
_session.mount("https://", HTTPAdapter(max_retries=Retry(
    total=3,
    connect=3,
    read=1,
    backoff_factor=0.5,
    status_forcelist=(429, 502, 503, 504),
    allowed_methods=("GET",),
)))


def _wait_for_rate_limit():
    """Serialize outgoing OSRM calls at no faster than 1 per second."""
    global _last_request_at
    with _rate_lock:
        now = time.monotonic()
        gap = now - _last_request_at
        if gap < _MIN_INTERVAL_S:
            time.sleep(_MIN_INTERVAL_S - gap)
        _last_request_at = time.monotonic()


def _osrm_get(url, params, timeout):
    """
    Shared request helper.
    Applies the process-wide rate limiter, then issues the request.
    """
    _wait_for_rate_limit()
    r = _session.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r


def get_route(start_latlon, end_latlon):
    """Return {"distance_m": int, "coords": [(lat, lon), ...]}."""
    slon, slat = start_latlon[1], start_latlon[0]
    elon, elat = end_latlon[1],   end_latlon[0]
    url = f"{OSRM_BASE}/{slon},{slat};{elon},{elat}"

    r = _osrm_get(url, params={
        "overview": "full",
        "geometries": "geojson",
        "steps": "false",
        "alternatives": "false",
    }, timeout=(_CONNECT_TIMEOUT, _ROUTE_READ_TIMEOUT))

    data = r.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RuntimeError(f"OSRM error: {data.get('code')}")

    route = data["routes"][0]
    geometry = route.get("geometry")

    if isinstance(geometry, dict):
        coords = [(c[1], c[0]) for c in geometry["coordinates"]]
    elif isinstance(geometry, str):
        raise RuntimeError(
            "OSRM returned polyline geometry, expected geojson. "
            "Check the 'geometries' query parameter."
        )
    else:
        raise RuntimeError(f"Unexpected geometry shape: {type(geometry)}")

    return {"distance_m": route["distance"], "coords": coords}


def highways_on_route(start_latlon, end_latlon):
    """Return set of highway refs (e.g. {'I-80', 'US-6'}) along the route."""
    slon, slat = start_latlon[1], start_latlon[0]
    elon, elat = end_latlon[1],   end_latlon[0]
    url = f"{OSRM_BASE}/{slon},{slat};{elon},{elat}"

    r = _osrm_get(url, params={
        "overview": "false",
        "steps": "true",
        "geometries": "polyline",    # much smaller than geojson
    }, timeout=(_CONNECT_TIMEOUT, _HIGHWAYS_READ_TIMEOUT))

    data = r.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RuntimeError(f"OSRM error: {data.get('code')}")

    highways = set()
    for leg in data["routes"][0]["legs"]:
        for step in leg["steps"]:
            ref = step.get("ref", "") or ""
            for h in re.split(r"[;/ ]+", ref):
                if h:
                    highways.add(h.strip().upper())
    return highways
