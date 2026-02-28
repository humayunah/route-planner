import pytest
from django.core.cache import cache as django_cache

from route_planner.models import FuelStation


@pytest.fixture(autouse=True)
def _clear_cache():
    """Prevent geocode cache from leaking between tests."""
    django_cache.clear()


@pytest.fixture
def fuel_stations(db):
    """Create a set of stations along a west-east route for testing."""
    stations_data = [
        {
            "opis_id": 1,
            "name": "Station A",
            "city": "Start City",
            "state": "NY",
            "address": "I-80",
            "rack_id": 100,
            "retail_price": 3.50,
            "latitude": 40.7,
            "longitude": -74.0,
        },
        {
            "opis_id": 2,
            "name": "Station B",
            "city": "Mid City 1",
            "state": "PA",
            "address": "I-80",
            "rack_id": 101,
            "retail_price": 3.20,
            "latitude": 40.8,
            "longitude": -76.0,
        },
        {
            "opis_id": 3,
            "name": "Station C",
            "city": "Mid City 2",
            "state": "OH",
            "address": "I-80",
            "rack_id": 102,
            "retail_price": 2.90,
            "latitude": 40.9,
            "longitude": -80.0,
        },
        {
            "opis_id": 4,
            "name": "Station D",
            "city": "Mid City 3",
            "state": "IN",
            "address": "I-80",
            "rack_id": 103,
            "retail_price": 3.10,
            "latitude": 41.0,
            "longitude": -85.0,
        },
        {
            "opis_id": 5,
            "name": "Station E",
            "city": "End City",
            "state": "IL",
            "address": "I-80",
            "rack_id": 104,
            "retail_price": 3.00,
            "latitude": 41.1,
            "longitude": -88.0,
        },
    ]
    return FuelStation.objects.bulk_create([FuelStation(**d) for d in stations_data])
