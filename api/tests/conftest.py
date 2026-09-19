import pytest
from decimal import Decimal

from api.models import FuelStation


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """
    Global kill-switch. Patches the names in `route_optimizer` itself,
    because that module does `from x import y` — patching `geocoder` or
    `osrm_client` would not affect the already-bound references.
    """
    from api.services import route_optimizer

    def _boom(*a, **kw):
        raise AssertionError("Test tried to hit an external API.")

    monkeypatch.setattr(route_optimizer, "geocode_address", _boom)
    monkeypatch.setattr(route_optimizer, "get_route", _boom)
    monkeypatch.setattr(route_optimizer, "highways_on_route", _boom)


@pytest.fixture
def make_station(db):
    counter = {"n": 0}

    def _make(
        *,
        opis_id=None,
        name="Test Stop",
        address="I-55 Exit 1",
        city="Springfield",
        state="IL",
        rack_id="",
        price="3.500000",
        latitude=39.0,
        longitude=-89.0,
    ):
        counter["n"] += 1
        return FuelStation.objects.create(
            opis_id=opis_id or str(counter["n"]),
            name=name,
            address=address,
            city=city,
            state=state,
            rack_id=rack_id,
            price=Decimal(price),
            latitude=latitude,
            longitude=longitude,
        )

    return _make