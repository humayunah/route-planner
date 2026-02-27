from route_planner.models import FuelStation, haversine


class TestHaversine:
    def test_same_point_returns_zero(self):
        assert haversine(40.0, -74.0, 40.0, -74.0) == 0.0

    def test_known_distance_nyc_to_la(self):
        # NYC to LA ~ 2451 miles great circle
        dist = haversine(40.7128, -74.0060, 34.0522, -118.2437)
        assert 2400 < dist < 2500

    def test_short_distance(self):
        # ~69 miles per degree of latitude
        dist = haversine(40.0, -74.0, 41.0, -74.0)
        assert 68 < dist < 70


class TestFuelStationManager:
    def test_near_route_finds_stations(self, fuel_stations):
        route_points = [
            (40.7, -74.0, 0),
            (40.8, -76.0, 100),
            (40.9, -80.0, 300),
            (41.0, -85.0, 500),
            (41.1, -88.0, 700),
        ]
        results = FuelStation.objects.near_route(route_points, buffer_miles=50)
        assert len(results) == 5

    def test_near_route_excludes_distant_stations(self, fuel_stations):
        route_points = [(30.0, -90.0, 0), (30.0, -91.0, 60)]
        results = FuelStation.objects.near_route(route_points, buffer_miles=25)
        assert len(results) == 0

    def test_find_optimal_stops_short_route(self):
        """Route shorter than max range needs no stops."""
        stops, cost, gallons = FuelStation.objects.find_optimal_stops(
            [], total_distance=200, max_range=500, mpg=10
        )
        assert stops == []
        assert cost == 0
        assert gallons == 20.0

    def test_find_optimal_stops_picks_cheapest(self, fuel_stations):
        stations_with_dist = [
            (fuel_stations[0], 100.0),  # $3.50
            (fuel_stations[1], 200.0),  # $3.20
            (fuel_stations[2], 350.0),  # $2.90 <- cheapest
            (fuel_stations[3], 600.0),  # $3.10
            (fuel_stations[4], 800.0),  # $3.00
        ]
        stops, _total_cost, total_gallons = FuelStation.objects.find_optimal_stops(
            stations_with_dist, total_distance=1000, max_range=500, mpg=10
        )
        assert len(stops) >= 2
        assert total_gallons == 100.0
        # First stop should be Station C ($2.90) - cheapest in first 500 miles
        assert stops[0]["station"].retail_price == 2.90

    def test_find_optimal_stops_handles_no_stations(self):
        stops, _cost, gallons = FuelStation.objects.find_optimal_stops(
            [], total_distance=1000, max_range=500, mpg=10
        )
        assert stops == []
        assert gallons == 100.0
