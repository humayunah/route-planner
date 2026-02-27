from __future__ import annotations

import csv
import json
import time
from pathlib import Path

import geonamescache
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
}  # fmt: skip

CACHE_FILE = Path(settings.BASE_DIR) / "geocode_cache.json"


def _build_city_lookup() -> dict[tuple[str, str], tuple[float, float]]:
    """Build (city_lower, state_abbr) -> (lat, lon) from bundled geonames data."""
    gc = geonamescache.GeonamesCache(min_city_population=500)
    us_states_map = gc.get_us_states()
    admin1_to_abbr = {v["code"]: k for k, v in us_states_map.items()}

    lookup: dict[tuple[str, str], tuple[float, float]] = {}
    for city in gc.get_cities().values():
        if city["countrycode"] != "US":
            continue
        abbr = admin1_to_abbr.get(city["admin1code"], "")
        lookup[(city["name"].lower().strip(), abbr)] = (city["latitude"], city["longitude"])
    return lookup


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
        """Geocode stations: local geonames first, Nominatim fallback for misses."""
        cache = json.loads(CACHE_FILE.read_text()) if CACHE_FILE.exists() else {}
        city_lookup = _build_city_lookup()

        ungeo = FuelStation.objects.filter(latitude__isnull=True)
        unique_cities = set(ungeo.values_list("city", "state"))
        to_resolve = {(c, s) for c, s in unique_cities if f"{c},{s}" not in cache}

        # Phase 1: local geonames lookup (instant)
        nominatim_needed = []
        for city, state in to_resolve:
            coords = city_lookup.get((city.lower().strip(), state))
            if coords:
                cache[f"{city},{state}"] = {"lat": coords[0], "lon": coords[1]}
            else:
                nominatim_needed.append((city, state))

        self.stdout.write(
            f"{len(to_resolve)} cities to resolve: "
            f"{len(to_resolve) - len(nominatim_needed)} from local data, "
            f"{len(nominatim_needed)} need Nominatim"
        )

        # Phase 2: Nominatim for remaining (rate-limited)
        for i, (city, state) in enumerate(nominatim_needed):
            key = f"{city},{state}"
            try:
                resp = requests.get(
                    f"{settings.NOMINATIM_BASE_URL}/search",
                    params={"q": f"{city}, {state}, USA", "format": "json", "limit": 1},
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
                else:
                    cache[key] = None
                time.sleep(1.1)
            except Exception as e:
                self.stderr.write(f"  Error geocoding {key}: {e}")
                cache[key] = None

            if (i + 1) % 50 == 0:
                self.stdout.write(f"  Nominatim: {i + 1}/{len(nominatim_needed)}")
                CACHE_FILE.write_text(json.dumps(cache, indent=2))

        CACHE_FILE.write_text(json.dumps(cache, indent=2))

        # Apply coordinates to stations
        updated = 0
        for station in FuelStation.objects.filter(latitude__isnull=True):
            coords = cache.get(f"{station.city},{station.state}")
            if coords:
                station.latitude = coords["lat"]
                station.longitude = coords["lon"]
                station.save(update_fields=["latitude", "longitude"])
                updated += 1

        self.stdout.write(f"Updated coordinates for {updated} stations")
