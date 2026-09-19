"""
Two focused tests for the trip optimizer (`plan_trip`).
"""
import pytest

from api.services import constants as C
from api.services import route_optimizer
from api.services.fuel_stations import haversine_km


CITY_A = ("Alpha", 39.0, -90.0)   # start
CITY_B = ("Bravo", 39.0, -88.0)   # finish


def _straight_route(lat, lon_start, lon_end, n=21):
    step = (lon_end - lon_start) / (n - 1)
    coords = [(lat, lon_start + i * step) for i in range(n)]
    total_km = sum(haversine_km(coords[i - 1], coords[i]) for i in range(1, n))
    return coords, total_km


@pytest.fixture
def fake_route(monkeypatch):
    """
    Patch the three outbound integrations on `route_optimizer`:
      - geocode_address("Alpha") → (39.0, -90.0)
      - geocode_address("Bravo") → (39.0, -88.0)
      - highways_on_route → ["I-55"]
      - get_route → straight polyline, true length via haversine

    Returns total_km so tests can assert against it.
    """
    coords, total_km = _straight_route(lat=39.0, lon_start=-90.0, lon_end=-88.0)

    def fake_geocode(q):
        if q == CITY_A[0]:
            return CITY_A[1], CITY_A[2]
        if q == CITY_B[0]:
            return CITY_B[1], CITY_B[2]
        raise ValueError(f"unknown query: {q}")

    monkeypatch.setattr(route_optimizer, "geocode_address", fake_geocode)
    monkeypatch.setattr(route_optimizer, "highways_on_route", lambda *_: ["I-55"])
    monkeypatch.setattr(route_optimizer, "get_route", lambda *_: {
        "coords": coords,
        "distance_m": total_km * 1000.0,
    })
    return total_km


@pytest.mark.django_db
def test_short_trip_needs_no_refueling_and_costs_zero(
    make_station, fake_route, monkeypatch,
):
    """
    Scenario 1 — short trip, under range, no refueling stops, zero cost.

    Route is ~170 km (~106 miles). Vehicle range set to 300 miles, so
    the whole trip fits on one tank. Even though an on-route station
    exists, the planner must return zero stops and zero cost.
    """
    make_station(
        opis_id="ignored",
        name="Alpha Travel Center",
        address="I-55 Exit 10",
        city="Alpha",
        state="IL",
        price="3.500000",
        latitude=39.0,
        longitude=-89.0,
    )

    monkeypatch.setattr(C, "MAX_RANGE_KM", 300 * C.MILES_TO_KM)
    monkeypatch.setattr(C, "MAX_RANGE_MILES", 300)
    monkeypatch.setattr(C, "SAFETY_MARGIN", 1.0)

    result = route_optimizer.plan_trip(CITY_A[0], CITY_B[0])

    assert result["stops"] == []
    assert result["total_cost"] == 0.0
    assert result["total_miles"] == pytest.approx(
        fake_route / C.MILES_TO_KM, abs=1.0,
    )


@pytest.mark.django_db
def test_long_trip_requires_refueling_stops(
    make_station, fake_route, monkeypatch,
):
    """
    Scenario 2 — long trip, over range, requires refueling stops.

    Same ~170 km route, but the range is 40 miles (~64 km) and the
    safety margin is 1.0, so each leg is exactly 40 mi. That forces the
    planner to pick at least one on-route station.
    """
    for i, lon in enumerate((-89.7, -89.4, -89.1, -88.8), start=1):
        make_station(
            opis_id=f"s{i}",
            name=f"Stop {i}",
            address="I-55 Exit 1",
            city="Midway",
            state="IL",
            price="3.500000",
            latitude=39.0,
            longitude=lon,
        )

    monkeypatch.setattr(C, "MAX_RANGE_KM", 40 * C.MILES_TO_KM)
    monkeypatch.setattr(C, "MAX_RANGE_MILES", 40)
    monkeypatch.setattr(C, "SAFETY_MARGIN", 1.0)

    result = route_optimizer.plan_trip(CITY_A[0], CITY_B[0])

    assert len(result["stops"]) >= 1
    assert result["total_cost"] > 0.0

    stop = result["stops"][0]
    for key in ("opis_id", "name", "price",
                "lat", "lon", "km_from_start",
                "mi_from_start", "detour_km", "detour_mi"):
        assert key in stop
