from unittest.mock import MagicMock, patch

import pytest

from route_planner.routing import geocode, get_route, sample_route


class TestGeocode:
    @patch("route_planner.routing.requests.get")
    def test_geocode_success(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [{"lat": "40.7128", "lon": "-74.006"}],
        )
        mock_get.return_value.raise_for_status = MagicMock()
        lat, lon = geocode("New York, NY")
        assert abs(lat - 40.7128) < 0.01
        assert abs(lon - (-74.006)) < 0.01

    @patch("route_planner.routing.requests.get")
    def test_geocode_not_found_raises(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [])
        mock_get.return_value.raise_for_status = MagicMock()
        with pytest.raises(ValueError, match="Could not geocode"):
            geocode("Nonexistent Place XYZ")


class TestGetRoute:
    @patch("route_planner.routing.requests.get")
    def test_get_route_success(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "code": "Ok",
                "routes": [
                    {
                        "distance": 100000,
                        "duration": 3600,
                        "geometry": "_p~iF~ps|U_ulLnnqC",
                    }
                ],
            },
        )
        mock_get.return_value.raise_for_status = MagicMock()
        result = get_route((40.7, -74.0), (41.0, -75.0))
        assert result["distance_miles"] > 0
        assert result["duration_seconds"] == 3600
        assert len(result["geometry"]) > 0
        assert len(result["sampled_points"]) > 0


class TestSampleRoute:
    def test_sample_route_basic(self):
        points = [(40.0, -74.0), (41.0, -74.0), (42.0, -74.0)]
        samples = sample_route(points, interval_miles=30)
        assert len(samples) >= 2
        assert samples[0][2] == 0.0
        assert samples[-1][2] > 100

    def test_sample_route_empty(self):
        assert sample_route([]) == []

    def test_sample_route_single_point(self):
        samples = sample_route([(40.0, -74.0)])
        assert len(samples) == 1


class TestGeocodEdgeCases:
    @patch("route_planner.routing.requests.get")
    def test_geocode_http_error(self, mock_get):
        """HTTP errors should propagate."""
        import requests

        mock_get.return_value = MagicMock(status_code=500)
        mock_get.return_value.raise_for_status.side_effect = requests.RequestException(
            "Server error"
        )
        with pytest.raises(requests.RequestException):
            geocode("Some Place")

    @patch("route_planner.routing.requests.get")
    def test_geocode_returns_first_result(self, mock_get):
        """Should use first result when multiple returned."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [
                {"lat": "40.0", "lon": "-74.0"},
                {"lat": "41.0", "lon": "-75.0"},
            ],
        )
        mock_get.return_value.raise_for_status = MagicMock()
        lat, lon = geocode("Ambiguous Place")
        assert lat == 40.0
        assert lon == -74.0


class TestGetRouteEdgeCases:
    @patch("route_planner.routing.requests.get")
    def test_get_route_osrm_error(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"code": "NoRoute", "routes": []},
        )
        mock_get.return_value.raise_for_status = MagicMock()
        with pytest.raises(ValueError, match="OSRM routing failed"):
            get_route((40.7, -74.0), (41.0, -75.0))


class TestSampleRouteEdgeCases:
    def test_sample_route_two_close_points(self):
        """Two points closer than interval should return start and end."""
        samples = sample_route([(40.0, -74.0), (40.001, -74.001)], interval_miles=30)
        assert len(samples) >= 1
        assert samples[0][2] == 0.0

    def test_sample_route_always_includes_endpoint(self):
        """Endpoint must always be included."""
        points = [(40.0, -74.0), (41.0, -74.0), (42.0, -74.0)]
        samples = sample_route(points, interval_miles=30)
        last_sample = samples[-1]
        assert abs(last_sample[0] - 42.0) < 0.01
        assert abs(last_sample[1] - (-74.0)) < 0.01

    def test_sample_route_cumulative_distance_monotonic(self):
        """Cumulative distance should always increase."""
        points = [
            (40.0, -74.0),
            (40.5, -74.5),
            (41.0, -75.0),
            (41.5, -75.5),
        ]
        samples = sample_route(points, interval_miles=10)
        for i in range(1, len(samples)):
            assert samples[i][2] > samples[i - 1][2]
