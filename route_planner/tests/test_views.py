from unittest.mock import MagicMock, patch

import pytest
from rest_framework.test import APIClient

from route_planner.models import FuelStation


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def stations_along_route(db):
    """Stations placed along a mock route."""
    return FuelStation.objects.bulk_create(
        [
            FuelStation(
                opis_id=10,
                name="Cheap Stop",
                city="Midway",
                state="PA",
                address="I-80",
                rack_id=1,
                retail_price=2.50,
                latitude=40.5,
                longitude=-76.0,
            ),
            FuelStation(
                opis_id=11,
                name="Far Stop",
                city="Westward",
                state="OH",
                address="I-80",
                rack_id=2,
                retail_price=3.00,
                latitude=40.6,
                longitude=-80.0,
            ),
        ]
    )


MOCK_OSRM_RESPONSE = {
    "code": "Ok",
    "routes": [
        {
            "distance": 800000,
            "duration": 28800,
            "geometry": "_p~iF~ps|U_ulLnnqC_mqNvxq`@",
        }
    ],
}

MOCK_NOMINATIM_RESPONSES = [
    [{"lat": "40.7128", "lon": "-74.006"}],
    [{"lat": "40.4406", "lon": "-79.9959"}],
]


class TestRouteView:
    @patch("route_planner.routing.requests.get")
    def test_route_success(self, mock_get, api_client, stations_along_route):
        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            url = args[0] if args else kwargs.get("url", "")
            if "nominatim" in url:
                resp = MagicMock(status_code=200)
                resp.json.return_value = MOCK_NOMINATIM_RESPONSES[min(call_count["n"], 1)]
                resp.raise_for_status = MagicMock()
                call_count["n"] += 1
                return resp
            else:
                resp = MagicMock(status_code=200)
                resp.json.return_value = MOCK_OSRM_RESPONSE
                resp.raise_for_status = MagicMock()
                return resp

        mock_get.side_effect = side_effect

        response = api_client.post(
            "/api/route/",
            {"start": "New York, NY", "finish": "Pittsburgh, PA"},
            format="json",
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_distance_miles" in data
        assert "fuel_stops" in data
        assert "route_geometry" in data
        assert "total_fuel_cost" in data
        assert isinstance(data["fuel_stops"], list)

    def test_route_missing_fields(self, api_client):
        response = api_client.post("/api/route/", {}, format="json")
        assert response.status_code == 400

    @patch("route_planner.routing.requests.get")
    def test_route_bad_geocode(self, mock_get, api_client):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [],
        )
        mock_get.return_value.raise_for_status = MagicMock()
        response = api_client.post(
            "/api/route/",
            {"start": "ZZZZZ", "finish": "YYYYY"},
            format="json",
        )
        assert response.status_code == 400
