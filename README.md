# Spotter Fuel Route Optimizer

A Django REST API that calculates the optimal fuel stops for a truck driving between any two US locations. Given a start and finish city, the API returns the full driving route, selects the cheapest fuel stations along the way, and provides a cost breakdown -- all using free, keyless external services.

## Quick Start

```bash
git clone <repo-url> && cd spotter-assessment

# Install dependencies (requires uv)
uv sync

# Create the database
uv run python manage.py migrate

# Load and geocode fuel stations (~1 min first run)
uv run python manage.py load_fuel_stations

# Start the server
uv run python manage.py runserver
```

The `load_fuel_stations` command processes the CSV in two phases:

1. **Local geocoding** -- resolves ~89% of station cities instantly via `geonamescache` (bundled offline data, no network calls).
2. **Nominatim fallback** -- geocodes the remaining ~11% via the free OpenStreetMap API at 1 req/sec. Results are cached to `geocode_cache.json` so subsequent runs are instant.

Final coverage: 6,599 of 6,626 unique stations (99.6%) have coordinates.

## API Reference

### POST /api/route/

**Request:**

```json
{
  "start": "New York, NY",
  "finish": "Los Angeles, CA"
}
```

**Response:**

```json
{
  "start": "New York, NY",
  "finish": "Los Angeles, CA",
  "total_distance_miles": 2775.8,
  "total_duration_hours": 40.3,
  "total_fuel_gallons": 277.58,
  "total_fuel_cost": 812.45,
  "fuel_stops": [
    {
      "station_name": "Fuel Mart",
      "address": "1200 Highway 30",
      "city": "Breezewood",
      "state": "PA",
      "latitude": 39.9993,
      "longitude": -78.2392,
      "retail_price": 2.879,
      "miles_from_start": 312.4,
      "gallons": 31.24,
      "cost": 89.94
    },
    {
      "station_name": "Quick Stop",
      "address": "500 Interstate Dr",
      "city": "Zanesville",
      "state": "OH",
      "latitude": 39.9403,
      "longitude": -82.0132,
      "retail_price": 2.749,
      "miles_from_start": 620.1,
      "gallons": 30.77,
      "cost": 84.59
    },
    {
      "station_name": "Midwest Fuel",
      "address": "800 Route 66",
      "city": "Tulsa",
      "state": "OK",
      "latitude": 36.1539,
      "longitude": -95.9928,
      "retail_price": 2.659,
      "miles_from_start": 1358.2,
      "gallons": 73.81,
      "cost": 196.26
    }
  ],
  "route_geometry": [[40.71275, -74.00597], [40.71193, -74.00811], "... lat/lon pairs for map rendering"]
}
```

**Error responses:**

| Status | Cause |
|--------|-------|
| 400 | Missing fields, empty strings, or unrecognizable location |
| 405 | Wrong HTTP method (only POST is accepted) |
| 502 | Geocoding or routing service unavailable |

## Architecture

The project follows a **fat models / thin views** pattern:

- **`FuelStation` model + `FuelStationManager`** -- contains all domain logic: bounding-box queries, haversine proximity filtering, and the greedy fuel stop optimizer. This keeps the business logic testable without HTTP concerns.
- **`routing.py`** -- thin utility module that wraps two external APIs (Nominatim geocoding and OSRM routing). Handles coordinate conversion, polyline decoding, and route sampling at configurable intervals.
- **`RouteView`** -- thin orchestrator that validates input, calls the utilities, delegates to the manager, and serializes the output. No business logic lives here.

**Per-request flow (3 external API calls):**

1. Geocode start location (Nominatim)
2. Geocode finish location (Nominatim)
3. Fetch driving route (OSRM)
4. Sample the polyline at 20-mile intervals
5. Query stations within 25 miles of the route (bounding box + haversine)
6. Run greedy optimizer to select cheapest stops

**Greedy optimization algorithm:**

The optimizer selects fuel stops by scanning forward along the route. At each decision point, it considers stations in the far half of the tank's range (250--500 miles ahead) and picks the cheapest one. This ensures stops are well-spaced and cost-effective. If no station exists in the preferred zone, it falls back to any reachable station.

## Tech Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Framework | Django 5.2 LTS + DRF | Mature ORM, built-in migrations, serialization |
| Routing | OSRM | Free driving directions, no API key required |
| Geocoding | Nominatim | Free OpenStreetMap geocoder, no API key required |
| Bulk geocoding | geonamescache | Offline city-to-coordinate lookup, no network calls |
| Database | SQLite | Zero config, sufficient for the station dataset |
| Package manager | uv | Fast dependency resolution and virtual env management |
| Linting | ruff | Fast Python linter and formatter |
| Type checking | ty | Lightweight type checker |
| Testing | pytest + pytest-django | Fixtures, parametrize, concise assertions |

No API keys or paid services are required to run this project.

## Data Pipeline

The `load_fuel_stations` management command processes the provided CSV:

1. **Parse** -- reads `fuel-prices-for-be-assessment.csv` (~8,151 rows)
2. **Filter** -- keeps only US state records (excludes non-US entries)
3. **Deduplicate** -- groups by OPIS Truckstop ID, keeps the lowest price per station -> **6,626 unique stations**
4. **Geocode (local)** -- matches city/state against `geonamescache` bundled data -> resolves ~89%
5. **Geocode (remote)** -- falls back to Nominatim for unmatched cities -> resolves ~11% more
6. **Cache** -- writes `geocode_cache.json` so re-runs skip all network calls
7. **Result** -- 6,599/6,626 stations have coordinates (99.6% coverage)

## Vehicle Assumptions

These are configurable in `config/settings.py`:

| Parameter | Value | Setting |
|-----------|-------|---------|
| Tank range | 500 miles | `VEHICLE_RANGE_MILES` |
| Fuel economy | 10 MPG | `VEHICLE_MPG` |
| Station search radius | 25 miles from route | `STATION_BUFFER_MILES` |
| Route sampling interval | 20 miles | `ROUTE_SAMPLE_INTERVAL_MILES` |

## Testing

```bash
uv run pytest -v
```

38 tests across three modules:

- **`test_models.py`** (18 tests) -- haversine distance calculations, manager queries (`near_route`, `find_optimal_stops`), queryset filters, edge cases (ungeocoded stations, empty inputs, spacing constraints)
- **`test_routing.py`** (12 tests) -- geocoding success/failure, OSRM integration, polyline sampling, boundary conditions (empty routes, close points, monotonic distances)
- **`test_views.py`** (8 tests) -- full request/response cycle, input validation, error handling (bad geocode, network failures, missing fields, wrong HTTP method), response structure verification

All external API calls are mocked. Tests run against an in-memory SQLite database.

## Development

```bash
uv run ruff check .      # lint
uv run ruff format .     # format
uv run ty check          # type check
```

## Project Structure

```
spotter-assessment/
  config/
    settings.py          # Django settings + route planner config
    urls.py              # Root URL config
  route_planner/
    models.py            # FuelStation model, manager, haversine
    routing.py           # Nominatim + OSRM API wrappers
    views.py             # RouteView (thin orchestrator)
    serializers.py       # Request/response serializers
    urls.py              # /api/route/ endpoint
    management/
      commands/
        load_fuel_stations.py  # CSV import + geocoding pipeline
    tests/
      conftest.py        # Shared fixtures
      test_models.py     # Model + manager tests
      test_routing.py    # Routing utility tests
      test_views.py      # API integration tests
  pyproject.toml         # Dependencies, tool config
  conftest.py            # pytest-django setup
```
