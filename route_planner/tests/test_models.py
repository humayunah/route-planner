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


class TestHaversineEdgeCases:
    def test_antipodal_points(self):
        """Opposite sides of Earth ~ 12,450 miles."""
        dist = haversine(0, 0, 0, 180)
        assert 12400 < dist < 12500

    def test_symmetric(self):
        """Distance A->B equals B->A."""
        d1 = haversine(40.7, -74.0, 34.0, -118.2)
        d2 = haversine(34.0, -118.2, 40.7, -74.0)
        assert d1 == d2


class TestFuelStationManagerEdgeCases:
    def test_near_route_with_ungeocoded_stations(self, db):
        """Stations without coordinates should be excluded."""
        FuelStation.objects.create(
            opis_id=99,
            name="No Coords",
            city="Nowhere",
            state="XX",
            address="n/a",
            rack_id=1,
            retail_price=3.0,
            latitude=None,
            longitude=None,
        )
        route_points = [(40.0, -74.0, 0), (41.0, -74.0, 69)]
        results = FuelStation.objects.near_route(route_points, buffer_miles=50)
        assert len(results) == 0

    def test_near_route_empty_points(self, db):
        """Empty route should return no stations."""
        results = FuelStation.objects.near_route([], buffer_miles=25)
        assert results == []

    def test_find_optimal_stops_single_stop_needed(self, fuel_stations):
        """Route of 600 miles needs exactly 1 stop."""
        stations_with_dist = [
            (fuel_stations[0], 200.0),  # $3.50
            (fuel_stations[2], 400.0),  # $2.90
        ]
        stops, _cost, gallons = FuelStation.objects.find_optimal_stops(
            stations_with_dist, total_distance=600, max_range=500, mpg=10
        )
        assert len(stops) == 1
        assert gallons == 60.0

    def test_find_optimal_stops_exact_range(self):
        """Route exactly equal to max range needs no stops."""
        stops, _cost, gallons = FuelStation.objects.find_optimal_stops(
            [], total_distance=500, max_range=500, mpg=10
        )
        assert stops == []
        assert gallons == 50.0

    def test_find_optimal_stops_respects_spacing(self, fuel_stations):
        """Should not pick stations too close together."""
        stations_with_dist = [
            (fuel_stations[0], 50.0),  # $3.50 - too close to start
            (fuel_stations[2], 300.0),  # $2.90
            (fuel_stations[1], 350.0),  # $3.20
            (fuel_stations[3], 700.0),  # $3.10
        ]
        stops, _, _ = FuelStation.objects.find_optimal_stops(
            stations_with_dist, total_distance=1000, max_range=500, mpg=10
        )
        # Should skip station at mile 50 (too close) and pick further ones
        if len(stops) >= 1:
            assert stops[0]["miles_from_start"] >= 250  # min_spacing = 500*0.5

    def test_find_optimal_stops_total_gallons_consistent(self, fuel_stations):
        """Total gallons should always equal total_distance / mpg."""
        stations_with_dist = [
            (fuel_stations[0], 200.0),
            (fuel_stations[2], 400.0),
            (fuel_stations[4], 700.0),
        ]
        stops, _cost, gallons = FuelStation.objects.find_optimal_stops(
            stations_with_dist, total_distance=900, max_range=500, mpg=10
        )
        assert gallons == 90.0
        # Sum of gallons across stops should approximate total
        if stops:
            stop_gallons = sum(s["gallons"] for s in stops)
            assert abs(stop_gallons - gallons) < 1.0  # rounding tolerance


class TestFuelStationQuerySet:
    def test_geocoded_excludes_null(self, db):
        FuelStation.objects.create(
            opis_id=90,
            name="Has Coords",
            city="A",
            state="NY",
            address="x",
            rack_id=1,
            retail_price=3.0,
            latitude=40.0,
            longitude=-74.0,
        )
        FuelStation.objects.create(
            opis_id=91,
            name="No Coords",
            city="B",
            state="NY",
            address="x",
            rack_id=1,
            retail_price=3.0,
            latitude=None,
            longitude=None,
        )
        assert FuelStation.objects.get_queryset().geocoded().count() == 1

    def test_in_bounding_box(self, db):
        FuelStation.objects.create(
            opis_id=92,
            name="Inside",
            city="A",
            state="NY",
            address="x",
            rack_id=1,
            retail_price=3.0,
            latitude=40.5,
            longitude=-74.5,
        )
        FuelStation.objects.create(
            opis_id=93,
            name="Outside",
            city="B",
            state="CA",
            address="x",
            rack_id=1,
            retail_price=3.0,
            latitude=34.0,
            longitude=-118.0,
        )
        results = FuelStation.objects.get_queryset().in_bounding_box(40.0, 41.0, -75.0, -74.0)
        assert results.count() == 1
        assert results.first().name == "Inside"
