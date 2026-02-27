# Fuel Route Optimizer API - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Django REST API that returns an optimal fuel-stop route between two US locations, minimizing fuel cost.

**Architecture:** Single Django app (`route_planner`) with a fat model/manager pattern. External API calls (OSRM routing, Nominatim geocoding) live in a thin `routing.py` utility module. Fuel stations loaded from CSV via management command with Nominatim geocoding cached to JSON. Greedy algorithm on the manager finds cheapest fuel stops within 500-mile vehicle range.

**Tech Stack:** Django 5.2 LTS, DRF, uv (env), ruff (lint/format), ty (type check), pytest + pytest-django, OSRM (routing), Nominatim (geocoding)

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `config/__init__.py`, `config/settings.py`, `config/urls.py`, `config/wsgi.py`
- Create: `manage.py`
- Create: `route_planner/__init__.py`
- Create: `conftest.py` (root)
- Create: `pytest.ini`

**Step 1: Create `pyproject.toml`**

```toml
[project]
name = "spotter-fuel-router"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "django>=5.2,<6",
    "djangorestframework>=3.15,<4",
    "requests>=2.32,<3",
    "polyline>=2.0,<3",
]

[tool.uv]
dev-dependencies = [
    "pytest>=8.3",
    "pytest-django>=4.9",
    "ruff>=0.9",
    "ty>=0.0.1a7",
]

[tool.ruff]
target-version = "py312"
line-length = 99

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "SIM", "RUF"]

[tool.ty]
python-version = "3.12"

[tool.ty.rules]
unresolved-attribute = "ignore"
unresolved-import = "ignore"
possibly-unresolved-reference = "ignore"

[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "config.settings"
pythonpath = ["."]
```

**Step 2: Create `config/settings.py`**

```python
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "dev-only-not-for-production"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "route_planner",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

ROOT_URLCONF = "config.urls"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "UNAUTHENTICATED_USER": None,
}

# Route planner settings
NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org"
OSRM_BASE_URL = "https://router.project-osrm.org"
VEHICLE_RANGE_MILES = 500
VEHICLE_MPG = 10
STATION_BUFFER_MILES = 25
ROUTE_SAMPLE_INTERVAL_MILES = 20
```

**Step 3: Create `config/urls.py`**

```python
from django.urls import include, path

urlpatterns = [
    path("api/", include("route_planner.urls")),
]
```

**Step 4: Create `config/wsgi.py`**

```python
import os
from django.core.wsgi import get_wsgi_application
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_wsgi_application()
```

**Step 5: Create `config/__init__.py`** (empty)

**Step 6: Create `manage.py`**

```python
#!/usr/bin/env python
import os
import sys

def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)

if __name__ == "__main__":
    main()
```

**Step 7: Create `route_planner/__init__.py`** (empty)

**Step 8: Create root `conftest.py`**

```python
import django
from django.conf import settings

def pytest_configure():
    if not settings.configured:
        settings.configure(
            DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
            INSTALLED_APPS=[
                "django.contrib.contenttypes",
                "django.contrib.auth",
                "rest_framework",
                "route_planner",
            ],
            ROOT_URLCONF="config.urls",
            DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
            NOMINATIM_BASE_URL="https://nominatim.openstreetmap.org",
            OSRM_BASE_URL="https://router.project-osrm.org",
            VEHICLE_RANGE_MILES=500,
            VEHICLE_MPG=10,
            STATION_BUFFER_MILES=25,
            ROUTE_SAMPLE_INTERVAL_MILES=20,
            REST_FRAMEWORK={
                "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
                "UNAUTHENTICATED_USER": None,
            },
        )
    django.setup()
```

**Step 9: Init env and verify**

```bash
cd /d/code/spotter-assessment
uv sync
uv run python manage.py check
```

**Step 10: Commit**

```bash
git init && git add -A && git commit -m "chore: scaffold Django project with uv, ruff, ty"
```

---

## Task 2: FuelStation Model + Manager

**Files:**
- Create: `route_planner/models.py`
- Create: `route_planner/migrations/` (auto-generated)

**Step 1: Write `route_planner/models.py`**

```python
from __future__ import annotations

import math

from django.db import models


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in miles between two (lat, lon) points."""
    R = 3959  # Earth radius in miles
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


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
        route_points: list[tuple[float, float]],
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
        Greedy cheapest-first fuel stop selection.

        Returns (stop_details, total_cost, total_gallons).
        Each stop_detail: {station, miles_from_start, gallons, cost}.
        """
        sorted_stations = sorted(stations_with_distances, key=lambda x: x[1])
        total_gallons = total_distance / mpg

        stops: list[tuple[FuelStation, float]] = []
        current_pos = 0.0

        while current_pos + max_range < total_distance:
            reachable = [
                (s, d) for s, d in sorted_stations if current_pos < d <= current_pos + max_range
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
        indexes = [models.Index(fields=["state", "city"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.city}, {self.state}) - ${self.retail_price:.3f}"
```

**Step 2: Create migration and verify**

```bash
uv run python manage.py makemigrations route_planner
uv run python manage.py migrate
```

**Step 3: Commit**

```bash
git add -A && git commit -m "feat: add FuelStation model with manager"
```

---

## Task 3: Routing Utilities (OSRM + Nominatim + helpers)

**Files:**
- Create: `route_planner/routing.py`

**Step 1: Write `route_planner/routing.py`**

```python
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


def get_route(
    start: tuple[float, float], finish: tuple[float, float]
) -> dict:
    """
    Fetch driving route from OSRM.
    Returns {distance_miles, duration_seconds, geometry_points: [(lat, lon, cum_miles)...]}.
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
```

**Step 2: Commit**

```bash
git add -A && git commit -m "feat: add OSRM routing and Nominatim geocoding utilities"
```

---

## Task 4: Management Command (load CSV + geocode stations)

**Files:**
- Create: `route_planner/management/__init__.py`
- Create: `route_planner/management/commands/__init__.py`
- Create: `route_planner/management/commands/load_fuel_stations.py`

**Step 1: Write management command**

```python
from __future__ import annotations

import csv
import json
import time
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from route_planner.models import FuelStation

US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
}

CACHE_FILE = Path(settings.BASE_DIR) / "geocode_cache.json"


class Command(BaseCommand):
    help = "Load fuel stations from CSV and geocode by city/state"

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv",
            default=str(Path(settings.BASE_DIR) / "fuel-prices-for-be-assessment.csv"),
        )
        parser.add_argument("--skip-geocoding", action="store_true")

    def handle(self, *args, **options):
        self._load_csv(options["csv"])
        if not options["skip_geocoding"]:
            self._geocode_stations()

    def _load_csv(self, csv_path: str) -> None:
        """Load CSV, deduplicate by OPIS ID (keep cheapest price)."""
        best: dict[int, dict] = {}
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                state = row["State"].strip()
                if state not in US_STATES:
                    continue
                try:
                    opis_id = int(row["OPIS Truckstop ID"])
                    price = float(row["Retail Price"])
                except (ValueError, KeyError):
                    continue

                if opis_id not in best or price < best[opis_id]["retail_price"]:
                    best[opis_id] = {
                        "opis_id": opis_id,
                        "name": row["Truckstop Name"].strip(),
                        "address": row["Address"].strip(),
                        "city": row["City"].strip(),
                        "state": state,
                        "rack_id": int(row["Rack ID"]),
                        "retail_price": price,
                    }

        created = 0
        for data in best.values():
            _, is_new = FuelStation.objects.update_or_create(
                opis_id=data["opis_id"], defaults=data
            )
            if is_new:
                created += 1

        self.stdout.write(f"Loaded {len(best)} stations ({created} new)")

    def _geocode_stations(self) -> None:
        """Geocode stations by city/state using Nominatim with JSON cache."""
        cache = json.loads(CACHE_FILE.read_text()) if CACHE_FILE.exists() else {}

        ungeo = FuelStation.objects.filter(latitude__isnull=True)
        unique_cities = set(ungeo.values_list("city", "state"))
        to_geocode = {(c, s) for c, s in unique_cities if f"{c},{s}" not in cache}

        self.stdout.write(
            f"{ungeo.count()} ungeocoded stations, "
            f"{len(to_geocode)} unique cities to geocode"
        )

        for city, state in to_geocode:
            key = f"{city},{state}"
            try:
                resp = requests.get(
                    f"{settings.NOMINATIM_BASE_URL}/search",
                    params={
                        "q": f"{city}, {state}, USA",
                        "format": "json",
                        "limit": 1,
                    },
                    headers={"User-Agent": "SpotterFuelRouter/1.0"},
                    timeout=10,
                )
                resp.raise_for_status()
                results = resp.json()
                if results:
                    cache[key] = {
                        "lat": float(results[0]["lat"]),
                        "lon": float(results[0]["lon"]),
                    }
                    self.stdout.write(f"  Geocoded: {key}")
                else:
                    cache[key] = None
                    self.stdout.write(f"  Not found: {key}")
                time.sleep(1.1)  # Nominatim rate limit
            except Exception as e:
                self.stderr.write(f"  Error geocoding {key}: {e}")
                cache[key] = None

            # Save cache periodically
            CACHE_FILE.write_text(json.dumps(cache, indent=2))

        # Apply cached coordinates to stations
        updated = 0
        for station in ungeo:
            key = f"{station.city},{station.state}"
            coords = cache.get(key)
            if coords:
                station.latitude = coords["lat"]
                station.longitude = coords["lon"]
                station.save(update_fields=["latitude", "longitude"])
                updated += 1

        self.stdout.write(f"Updated coordinates for {updated} stations")
```

**Step 2: Commit**

```bash
git add -A && git commit -m "feat: add load_fuel_stations management command"
```

---

## Task 5: API View + Serializer

**Files:**
- Create: `route_planner/serializers.py`
- Create: `route_planner/views.py`
- Create: `route_planner/urls.py`

**Step 1: Write `route_planner/serializers.py`**

```python
from __future__ import annotations

from rest_framework import serializers


class RouteRequestSerializer(serializers.Serializer):
    start = serializers.CharField(help_text="Start location (e.g. 'New York, NY')")
    finish = serializers.CharField(help_text="Finish location (e.g. 'Los Angeles, CA')")


class FuelStopSerializer(serializers.Serializer):
    station_name = serializers.CharField()
    address = serializers.CharField()
    city = serializers.CharField()
    state = serializers.CharField()
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    retail_price = serializers.FloatField()
    miles_from_start = serializers.FloatField()
    gallons = serializers.FloatField()
    cost = serializers.FloatField()


class RouteResponseSerializer(serializers.Serializer):
    start = serializers.CharField()
    finish = serializers.CharField()
    total_distance_miles = serializers.FloatField()
    total_duration_hours = serializers.FloatField()
    total_fuel_gallons = serializers.FloatField()
    total_fuel_cost = serializers.FloatField()
    fuel_stops = FuelStopSerializer(many=True)
    route_geometry = serializers.ListField(
        child=serializers.ListField(child=serializers.FloatField())
    )
```

**Step 2: Write `route_planner/views.py`**

```python
from __future__ import annotations

from django.conf import settings
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import FuelStation
from .routing import geocode, get_route
from .serializers import RouteRequestSerializer, RouteResponseSerializer


class RouteView(APIView):
    def post(self, request: Request) -> Response:
        ser = RouteRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        try:
            start_coords = geocode(ser.validated_data["start"])
            finish_coords = geocode(ser.validated_data["finish"])
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            route = get_route(start_coords, finish_coords)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_502_BAD_GATEWAY)

        stations_near = FuelStation.objects.near_route(
            route["sampled_points"],
            buffer_miles=settings.STATION_BUFFER_MILES,
        )

        stops, total_cost, total_gallons = FuelStation.objects.find_optimal_stops(
            stations_near,
            route["distance_miles"],
            max_range=settings.VEHICLE_RANGE_MILES,
            mpg=settings.VEHICLE_MPG,
        )

        fuel_stops = [
            {
                "station_name": s["station"].name,
                "address": s["station"].address,
                "city": s["station"].city,
                "state": s["station"].state,
                "latitude": s["station"].latitude,
                "longitude": s["station"].longitude,
                "retail_price": s["station"].retail_price,
                "miles_from_start": s["miles_from_start"],
                "gallons": s["gallons"],
                "cost": s["cost"],
            }
            for s in stops
        ]

        response_data = {
            "start": ser.validated_data["start"],
            "finish": ser.validated_data["finish"],
            "total_distance_miles": route["distance_miles"],
            "total_duration_hours": round(route["duration_seconds"] / 3600, 1),
            "total_fuel_gallons": total_gallons,
            "total_fuel_cost": total_cost,
            "fuel_stops": fuel_stops,
            "route_geometry": route["geometry"],
        }

        out = RouteResponseSerializer(response_data)
        return Response(out.data)
```

**Step 3: Write `route_planner/urls.py`**

```python
from django.urls import path

from .views import RouteView

urlpatterns = [
    path("route/", RouteView.as_view(), name="route"),
]
```

**Step 4: Verify app loads**

```bash
uv run python manage.py check
```

**Step 5: Commit**

```bash
git add -A && git commit -m "feat: add route API endpoint"
```

---

## Task 6: Tests

**Files:**
- Create: `route_planner/tests/__init__.py`
- Create: `route_planner/tests/conftest.py`
- Create: `route_planner/tests/test_models.py`
- Create: `route_planner/tests/test_routing.py`
- Create: `route_planner/tests/test_views.py`

**Step 1: Write `route_planner/tests/conftest.py`**

```python
import pytest
from route_planner.models import FuelStation


@pytest.fixture
def fuel_stations(db):
    """Create a set of stations along a west-east route for testing."""
    stations_data = [
        {"opis_id": 1, "name": "Station A", "city": "Start City", "state": "NY",
         "address": "I-80", "rack_id": 100, "retail_price": 3.50,
         "latitude": 40.7, "longitude": -74.0},
        {"opis_id": 2, "name": "Station B", "city": "Mid City 1", "state": "PA",
         "address": "I-80", "rack_id": 101, "retail_price": 3.20,
         "latitude": 40.8, "longitude": -76.0},
        {"opis_id": 3, "name": "Station C", "city": "Mid City 2", "state": "OH",
         "address": "I-80", "rack_id": 102, "retail_price": 2.90,
         "latitude": 40.9, "longitude": -80.0},
        {"opis_id": 4, "name": "Station D", "city": "Mid City 3", "state": "IN",
         "address": "I-80", "rack_id": 103, "retail_price": 3.10,
         "latitude": 41.0, "longitude": -85.0},
        {"opis_id": 5, "name": "Station E", "city": "End City", "state": "IL",
         "address": "I-80", "rack_id": 104, "retail_price": 3.00,
         "latitude": 41.1, "longitude": -88.0},
    ]
    return FuelStation.objects.bulk_create(
        [FuelStation(**d) for d in stations_data]
    )
```

**Step 2: Write `route_planner/tests/test_models.py`**

```python
import pytest
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
        # Route points roughly along I-80 corridor
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
        # Route far from all stations
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
            (fuel_stations[0], 100.0),   # $3.50
            (fuel_stations[1], 200.0),   # $3.20
            (fuel_stations[2], 350.0),   # $2.90 <- cheapest
            (fuel_stations[3], 600.0),   # $3.10
            (fuel_stations[4], 800.0),   # $3.00
        ]
        stops, total_cost, total_gallons = FuelStation.objects.find_optimal_stops(
            stations_with_dist, total_distance=1000, max_range=500, mpg=10
        )
        # Should pick cheapest reachable station each time
        assert len(stops) >= 2
        assert total_gallons == 100.0
        # First stop should be Station C ($2.90) - cheapest in first 500 miles
        assert stops[0]["station"].retail_price == 2.90

    def test_find_optimal_stops_handles_no_stations(self):
        stops, cost, gallons = FuelStation.objects.find_optimal_stops(
            [], total_distance=1000, max_range=500, mpg=10
        )
        assert stops == []
        assert gallons == 100.0
```

**Step 3: Write `route_planner/tests/test_routing.py`**

```python
from unittest.mock import patch, MagicMock
import pytest
from route_planner.routing import geocode, get_route, sample_route


class TestGeocode:
    @patch("route_planner.routing.requests.get")
    def test_geocode_success(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [{"lat": "40.7128", "lon": "-74.006"}],
        )
        lat, lon = geocode("New York, NY")
        assert abs(lat - 40.7128) < 0.01
        assert abs(lon - (-74.006)) < 0.01

    @patch("route_planner.routing.requests.get")
    def test_geocode_not_found_raises(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [])
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
                        "distance": 100000,  # 100km ~ 62 miles
                        "duration": 3600,
                        "geometry": "_p~iF~ps|U_ulLnnqC",  # sample polyline
                    }
                ],
            },
        )
        result = get_route((40.7, -74.0), (41.0, -75.0))
        assert result["distance_miles"] > 0
        assert result["duration_seconds"] == 3600
        assert len(result["geometry"]) > 0
        assert len(result["sampled_points"]) > 0


class TestSampleRoute:
    def test_sample_route_basic(self):
        # Points ~69 miles apart (1 degree lat)
        points = [(40.0, -74.0), (41.0, -74.0), (42.0, -74.0)]
        samples = sample_route(points, interval_miles=30)
        assert len(samples) >= 2
        assert samples[0][2] == 0.0  # first point cumulative = 0
        assert samples[-1][2] > 100  # total > 100 miles

    def test_sample_route_empty(self):
        assert sample_route([]) == []

    def test_sample_route_single_point(self):
        samples = sample_route([(40.0, -74.0)])
        assert len(samples) == 1
```

**Step 4: Write `route_planner/tests/test_views.py`**

```python
from unittest.mock import patch, MagicMock
import pytest
from django.test import override_settings
from rest_framework.test import APIClient
from route_planner.models import FuelStation


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def stations_along_route(db):
    """Stations placed along a mock route."""
    return FuelStation.objects.bulk_create([
        FuelStation(opis_id=10, name="Cheap Stop", city="Midway", state="PA",
                    address="I-80", rack_id=1, retail_price=2.50,
                    latitude=40.5, longitude=-76.0),
        FuelStation(opis_id=11, name="Far Stop", city="Westward", state="OH",
                    address="I-80", rack_id=2, retail_price=3.00,
                    latitude=40.6, longitude=-80.0),
    ])


MOCK_OSRM_RESPONSE = {
    "code": "Ok",
    "routes": [{
        "distance": 800000,  # ~497 miles
        "duration": 28800,
        "geometry": "_p~iF~ps|U_ulLnnqC_mqNvxq`@",
    }],
}

MOCK_NOMINATIM_RESPONSES = [
    [{"lat": "40.7128", "lon": "-74.006"}],   # start
    [{"lat": "40.4406", "lon": "-79.9959"}],   # finish
]


class TestRouteView:
    @patch("route_planner.routing.requests.get")
    def test_route_success(self, mock_get, api_client, stations_along_route):
        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            url = args[0] if args else kwargs.get("url", "")
            if "nominatim" in url:
                resp = MagicMock(status_code=200)
                resp.json.return_value = MOCK_NOMINATIM_RESPONSES[
                    min(call_count["n"], 1)
                ]
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
```

**Step 5: Run all tests**

```bash
uv run pytest -v
```

**Step 6: Commit**

```bash
git add -A && git commit -m "test: add comprehensive tests for models, routing, and views"
```

---

## Task 7: Lint, Type-check, Final Verification

**Step 1: Run ruff**

```bash
uv run ruff check . --fix
uv run ruff format .
```

**Step 2: Run ty**

```bash
uv run ty check
```

**Step 3: Run full test suite**

```bash
uv run pytest -v --tb=short
```

**Step 4: Manual smoke test (after loading data)**

```bash
uv run python manage.py migrate
uv run python manage.py load_fuel_stations --skip-geocoding
# then with geocoding if cache exists:
uv run python manage.py load_fuel_stations
```

**Step 5: Final commit**

```bash
git add -A && git commit -m "chore: lint, format, type-check pass"
```

---

## Task 8: Load Data + Geocode Stations

This is a runtime task (not code). Run the management command to populate the database:

```bash
uv run python manage.py load_fuel_stations
```

This will:
1. Load ~6700 unique US stations from CSV (deduped by cheapest price per OPIS ID)
2. Geocode ~3900 unique city/state pairs via Nominatim (~65 min first run)
3. Cache results to `geocode_cache.json` for instant subsequent runs

**After geocoding, test the API:**

```bash
uv run python manage.py runserver
# In another terminal:
curl -X POST http://localhost:8000/api/route/ \
  -H "Content-Type: application/json" \
  -d '{"start": "New York, NY", "finish": "Los Angeles, CA"}'
```
