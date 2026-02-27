from __future__ import annotations

import polyline as polyline_lib
import requests
from django.conf import settings

from .models import haversine


def geocode(place: str) -> tuple[float, float]:
    """Geocode a place name to (lat, lon) via Nominatim."""
    resp = requests.get(
        f"{settings.NOMINATIM_BASE_URL}/search",
        params={"q": place, "format": "json", "limit": 1, "countrycodes": "us"},
        headers={"User-Agent": "SpotterFuelRouter/1.0"},
        timeout=10,
    )
    resp.raise_for_status()
    results = resp.json()
    if not results:
        raise ValueError(f"Could not geocode: {place}")
    return float(results[0]["lat"]), float(results[0]["lon"])


def get_route(start: tuple[float, float], finish: tuple[float, float]) -> dict:
    """
    Fetch driving route from OSRM.
    Returns {distance_miles, duration_seconds, geometry: [(lat, lon)...], sampled_points: [(lat, lon, cum_miles)...]}.
    """
    # OSRM expects lon,lat
    coords = f"{start[1]},{start[0]};{finish[1]},{finish[0]}"
    resp = requests.get(
        f"{settings.OSRM_BASE_URL}/route/v1/driving/{coords}",
        params={"overview": "full", "geometries": "polyline"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("code") != "Ok" or not data.get("routes"):
        raise ValueError(f"OSRM routing failed: {data.get('code', 'unknown')}")

    route = data["routes"][0]
    distance_miles = route["distance"] * 0.000621371  # meters to miles
    duration_seconds = route["duration"]

    # Decode polyline and build sampled route with cumulative distances
    raw_points = polyline_lib.decode(route["geometry"])
    sampled = sample_route(raw_points, interval_miles=settings.ROUTE_SAMPLE_INTERVAL_MILES)

    return {
        "distance_miles": round(distance_miles, 1),
        "duration_seconds": round(duration_seconds),
        "geometry": raw_points,
        "sampled_points": sampled,
    }


def sample_route(
    points: list[tuple[float, float]], interval_miles: float = 20
) -> list[tuple[float, float, float]]:
    """
    Sample decoded polyline at regular intervals.
    Returns [(lat, lon, cumulative_miles), ...].
    """
    if not points:
        return []

    samples: list[tuple[float, float, float]] = [(points[0][0], points[0][1], 0.0)]
    cumulative = 0.0

    for i in range(1, len(points)):
        seg = haversine(points[i - 1][0], points[i - 1][1], points[i][0], points[i][1])
        cumulative += seg
        if cumulative - samples[-1][2] >= interval_miles:
            samples.append((points[i][0], points[i][1], cumulative))

    # Always include endpoint
    last = points[-1]
    if samples[-1][2] < cumulative:
        samples.append((last[0], last[1], cumulative))

    return samples
