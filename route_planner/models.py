from __future__ import annotations

import math
import typing

from django.db import models


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in miles between two (lat, lon) points."""
    earth_radius = 3959  # miles
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return earth_radius * 2 * math.asin(math.sqrt(a))


class FuelStationQuerySet(models.QuerySet):
    def geocoded(self):
        return self.exclude(latitude__isnull=True)

    def in_bounding_box(self, min_lat: float, max_lat: float, min_lon: float, max_lon: float):
        return self.geocoded().filter(
            latitude__gte=min_lat,
            latitude__lte=max_lat,
            longitude__gte=min_lon,
            longitude__lte=max_lon,
        )


class FuelStationManager(models.Manager):
    def get_queryset(self):
        return FuelStationQuerySet(self.model, using=self._db)

    def near_route(
        self,
        route_points: list[tuple[float, float, float]],
        buffer_miles: float = 25,
    ) -> list[tuple[FuelStation, float]]:
        """
        Return stations within buffer_miles of route, paired with their
        approximate distance-along-route (miles from start).

        route_points: list of (lat, lon, cumulative_miles) tuples sampled from route.
        """
        if not route_points:
            return []

        lats = [p[0] for p in route_points]
        lons = [p[1] for p in route_points]
        buffer_deg = buffer_miles / 69.0

        candidates = self.get_queryset().in_bounding_box(
            min(lats) - buffer_deg,
            max(lats) + buffer_deg,
            min(lons) - buffer_deg,
            max(lons) + buffer_deg,
        )

        results = []
        for station in candidates:
            best_dist = float("inf")
            best_route_mi = 0.0
            for lat, lon, cum_mi in route_points:
                d = haversine(station.latitude, station.longitude, lat, lon)
                if d < best_dist:
                    best_dist = d
                    best_route_mi = cum_mi
            if best_dist <= buffer_miles:
                results.append((station, best_route_mi))

        return results

    def find_optimal_stops(
        self,
        stations_with_distances: list[tuple[FuelStation, float]],
        total_distance: float,
        max_range: float = 500,
        mpg: float = 10,
    ) -> tuple[list[dict], float, float]:
        """
        Greedy cheapest-first fuel stop selection with minimum spacing.

        Picks the cheapest station in the second half of the tank's range,
        ensuring stops are well-spaced (~250-500 miles apart).

        Returns (stop_details, total_cost, total_gallons).
        Each stop_detail: {station, miles_from_start, gallons, cost}.
        """
        sorted_stations = sorted(stations_with_distances, key=lambda x: x[1])
        total_gallons = total_distance / mpg

        stops: list[tuple[FuelStation, float]] = []
        current_pos = 0.0
        min_spacing = max_range * 0.5  # don't stop until at least half-tank used

        while current_pos + max_range < total_distance:
            # Prefer stations in the far half of range (well-spaced stops)
            far_candidates = [
                (s, d)
                for s, d in sorted_stations
                if current_pos + min_spacing <= d <= current_pos + max_range
            ]
            if far_candidates:
                best = min(far_candidates, key=lambda x: x[0].retail_price)
            else:
                # Fallback: any reachable station
                reachable = [
                    (s, d)
                    for s, d in sorted_stations
                    if current_pos < d <= current_pos + max_range
                ]
                if not reachable:
                    break
                best = min(reachable, key=lambda x: x[0].retail_price)
            stops.append(best)
            current_pos = best[1]

        # Build cost breakdown
        details = []
        prev = 0.0
        for station, dist in stops:
            leg_gallons = (dist - prev) / mpg
            details.append(
                {
                    "station": station,
                    "miles_from_start": round(dist, 1),
                    "gallons": round(leg_gallons, 2),
                    "cost": round(leg_gallons * station.retail_price, 2),
                }
            )
            prev = dist

        # Final leg fuel (purchased at last stop)
        if details:
            final_gallons = (total_distance - prev) / mpg
            details[-1]["gallons"] = round(details[-1]["gallons"] + final_gallons, 2)
            details[-1]["cost"] = round(
                details[-1]["gallons"] * details[-1]["station"].retail_price, 2
            )

        total_cost = sum(d["cost"] for d in details)
        return details, round(total_cost, 2), round(total_gallons, 2)


class FuelStation(models.Model):
    opis_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=500)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=10)
    rack_id = models.IntegerField()
    retail_price = models.FloatField()
    latitude = models.FloatField(null=True, blank=True, db_index=True)
    longitude = models.FloatField(null=True, blank=True, db_index=True)

    objects = FuelStationManager()

    class Meta:
        indexes: typing.ClassVar = [models.Index(fields=["state", "city"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.city}, {self.state}) - ${self.retail_price:.3f}"
