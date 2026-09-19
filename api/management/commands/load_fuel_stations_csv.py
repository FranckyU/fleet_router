import csv
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from api.models import FuelStation


class Command(BaseCommand):
    help = (
        "Load fuel stations from the CSV into the database and enrich them "
        "with latitude/longitude from uscities.csv (matched on city+state). "
        "Idempotent: safe to re-run. New rows are inserted via the "
        "(opis_id, name, price) unique constraint; existing rows missing "
        "coordinates are backfilled in place."
        "run with 'docker compose exec web python manage.py load_fuel_stations_csv'"
    )

    # How many rows to update per bulk_update call during backfill.
    BATCH_SIZE = 1000

    def add_arguments(self, parser):
        parser.add_argument(
            "--stations-csv",
            default=None,
            help="Override path to the fuel stations CSV (default: settings.FUEL_CSV_PATH).",
        )
        parser.add_argument(
            "--cities-csv",
            default=None,
            help="Override path to the cities CSV (default: DATA_DIR/uscities.csv).",
        )

    def handle(self, *args, **opts):
        stations_path = settings.FUEL_CSV_PATH
        cities_path = settings.US_CITIES_CSV_PATH

        if not stations_path.exists():
            raise CommandError(f"Fuel stations CSV not found at {stations_path}")
        if not cities_path.exists():
            raise CommandError(f"Cities CSV not found at {cities_path}")

        # 1. Build (city_lower, state_upper) -> (lat, lng) lookup.
        coords = self._load_city_coords(cities_path)
        self.stdout.write(f"Loaded {len(coords)} city coordinates.")

        # 2. Parse the stations CSV and insert any new rows.
        rows, skipped, enriched = self._parse_stations(stations_path, coords)
        if not rows:
            raise CommandError("Stations CSV had no valid rows.")

        with transaction.atomic():
            FuelStation.objects.bulk_create(rows, ignore_conflicts=True)

        self.stdout.write(
            f"Stations CSV: parsed {len(rows)} rows "
            f"(skipped {skipped} malformed, {enriched} had coords)."
        )

        # 3. Backfill coordinates on any existing rows still missing them.
        self._backfill_coords(coords)

        # 4. Summary.
        total = FuelStation.objects.count()
        geocoded = FuelStation.objects.filter(
            latitude__isnull=False, longitude__isnull=False
        ).count()
        self.stdout.write(self.style.SUCCESS(
            f"Total stations: {total} | geocoded: {geocoded} | "
            f"still missing coords: {total - geocoded}."
        ))

    # ------------------------------------------------------------------ #
    # Load
    # ------------------------------------------------------------------ #
    def _parse_stations(self, path, coords):
        """
        Parse the fuel stations CSV and return (rows, skipped, enriched).
        Coordinates are attached when a (city, state) match exists.
        """
        rows = []
        skipped = 0
        enriched = 0
        now = timezone.now()

        with open(path, newline="", encoding="utf-8") as f:
            for raw in csv.DictReader(f):
                try:
                    price = Decimal(raw["Retail Price"].strip())
                except (InvalidOperation, KeyError, AttributeError):
                    skipped += 1
                    continue

                opis_id = (raw.get("OPIS Truckstop ID") or "").strip()
                name = (raw.get("Truckstop Name") or "").strip()
                if not opis_id or not name:
                    skipped += 1
                    continue

                city = (raw.get("City") or "").strip()
                state = (raw.get("State") or "").strip().upper()

                lat, lng = coords.get((city.lower(), state), (None, None))
                if lat is not None and lng is not None:
                    enriched += 1
                    geocoded_at = now
                else:
                    geocoded_at = None

                rows.append(FuelStation(
                    opis_id=opis_id,
                    name=name,
                    address=(raw.get("Address") or "").strip(),
                    city=city,
                    state=state,
                    rack_id=(raw.get("Rack ID") or "").strip(),
                    price=price,
                    latitude=lat,
                    longitude=lng,
                    geocoded_at=geocoded_at,
                ))

        return rows, skipped, enriched

    # ------------------------------------------------------------------ #
    # Backfill
    # ------------------------------------------------------------------ #
    def _backfill_coords(self, coords):
        """
        Update latitude/longitude/geocoded_at on existing rows that are
        missing coordinates, using the (city, state) lookup.
        """
        qs = FuelStation.objects.filter(
            latitude__isnull=True, longitude__isnull=True
        ).only("id", "city", "state", "latitude", "longitude", "geocoded_at")

        missing = qs.count()
        if missing == 0:
            self.stdout.write("Backfill: no rows missing coordinates.")
            return

        self.stdout.write(f"Backfill: {missing} rows to consider.")

        now = timezone.now()
        batch = []
        matched = 0
        unmatched = 0

        for station in qs.iterator(chunk_size=self.BATCH_SIZE):
            lat, lng = coords.get(
                (station.city.lower(), station.state.upper()), (None, None)
            )
            if lat is None or lng is None:
                unmatched += 1
                continue

            station.latitude = lat
            station.longitude = lng
            station.geocoded_at = now
            batch.append(station)
            matched += 1

            if len(batch) >= self.BATCH_SIZE:
                FuelStation.objects.bulk_update(
                    batch, ["latitude", "longitude", "geocoded_at"]
                )
                batch.clear()

        if batch:
            FuelStation.objects.bulk_update(
                batch, ["latitude", "longitude", "geocoded_at"]
            )

        self.stdout.write(self.style.SUCCESS(
            f"Backfill complete: {matched} rows updated, "
            f"{unmatched} could not be matched to a city."
        ))

    # ------------------------------------------------------------------ #
    # Lookup builder
    # ------------------------------------------------------------------ #
    @staticmethod
    def _load_city_coords(path):
        """
        Read uscities.csv and return a dict mapping
        (city_lower, state_id_upper) -> (lat, lng).

        Expected columns: city, city_ascii, state_id, state_name, lat, lng, ...
        """
        lookup = {}
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for raw in reader:
                city = (raw.get("city") or raw.get("city_ascii") or "").strip()
                state = (raw.get("state_id") or "").strip().upper()
                lat_s = (raw.get("lat") or "").strip()
                lng_s = (raw.get("lng") or "").strip()
                if not city or not state or not lat_s or not lng_s:
                    continue
                try:
                    lat = float(lat_s)
                    lng = float(lng_s)
                except ValueError:
                    continue

                # First match wins (file is ranked by population).
                lookup.setdefault((city.lower(), state), (lat, lng))
        return lookup
