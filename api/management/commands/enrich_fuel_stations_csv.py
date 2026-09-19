import csv
import time
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "fleet-router/1.0 (student project)"}


class Command(BaseCommand):
    help = (
        "Geocode the fuel-prices CSV by City/State and write a new CSV "
        "with latitude and longitude columns appended. "
        "Caches results in-memory so each unique City/State is geocoded once."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default=None,
            help="Output CSV path (default: <input>_geocoded.csv)",
        )

    def handle(self, *args, **opts):
        in_path = Path(settings.FUEL_CSV_PATH)
        if not in_path.exists():
            raise CommandError(f"CSV not found at {in_path}")

        out_path = opts["output"] or in_path.with_name(
            in_path.stem + "_geocoded" + in_path.suffix
        )

        # Cache keyed by (city, state) so each unique location is geocoded
        # exactly once, no matter how many rows reference it.
        coord_cache = {}

        rows_out = []
        total = 0
        geocoded = 0
        failures = 0

        with open(in_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = list(reader.fieldnames) + ["latitude", "longitude"]

            for raw in reader:
                total += 1
                city  = (raw.get("City")  or "").strip()
                state = (raw.get("State") or "").strip().upper()

                cache_key = (city.lower(), state)
                lat = lon = None

                if cache_key in coord_cache:
                    lat, lon = coord_cache[cache_key]
                else:
                    lat, lon = self._geocode(city, state)
                    if lat is not None:
                        coord_cache[cache_key] = (lat, lon)
                        geocoded += 1
                    else:
                        failures += 1

                raw["latitude"]  = "" if lat is None else f"{lat:.6f}"
                raw["longitude"] = "" if lon is None else f"{lon:.6f}"
                rows_out.append(raw)

                if total % 50 == 0:
                    self.stdout.write(
                        f"  {total} rows processed, "
                        f"{geocoded} unique cities geocoded, {failures} failures"
                    )

        # ---- Write the enriched CSV ----
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows_out)

        self.stdout.write(self.style.SUCCESS(
            f"Wrote {len(rows_out)} rows to {out_path} "
            f"({geocoded} unique cities geocoded, {failures} failures)."
        ))

    def _geocode(self, city, state):
        """Return (lat, lon) or (None, None) on failure."""
        if not city or not state:
            return None, None

        query = f"{city}, {state}"
        try:
            r = requests.get(
                NOMINATIM_URL,
                params={
                    "q": query,
                    "format": "json",
                    "limit": 1,
                    "countrycodes": "us",
                },
                headers=HEADERS,
                timeout=(10, 30),
            )
            r.raise_for_status()
            data = r.json()
            if not data:
                self.stderr.write(f"  ! no result for '{query}'")
                return None, None
            # Nominatim politeness: 1 request/second
            time.sleep(1.1)
            return float(data[0]["lat"]), float(data[0]["lon"])
        except Exception as e:
            self.stderr.write(f"  ! geocode failed for '{query}': {e}")
            return None, None
