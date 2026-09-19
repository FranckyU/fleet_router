from django.db import models


class FuelStation(models.Model):
    opis_id      = models.CharField(max_length=32, db_index=True)
    name         = models.CharField(max_length=255)
    address      = models.CharField(max_length=255, blank=True)
    city         = models.CharField(max_length=128, db_index=True)
    state        = models.CharField(max_length=2, db_index=True)
    rack_id      = models.CharField(max_length=32, blank=True)
    price        = models.DecimalField(max_digits=8, decimal_places=6, db_index=True)

    # Filled lazily by the geocoder; null until first use.
    latitude     = models.FloatField(null=True, blank=True)
    longitude    = models.FloatField(null=True, blank=True)
    geocoded_at  = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["opis_id", "name", "price"],
                name="uniq_station_row",
            ),
        ]
        indexes = [
            models.Index(fields=["state", "price"]),
            models.Index(fields=["latitude", "longitude"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state}) ${self.price}"

    @property
    def is_geocoded(self) -> bool:
        return self.latitude is not None and self.longitude is not None


class CachedRoute(models.Model):
    """
    One row per (start, finish) pair. Stores the full plan result so
    repeated queries skip OSRM and Nominatim entirely.
    """
    start_query  = models.CharField(max_length=255)
    finish_query = models.CharField(max_length=255)
    cache_key    = models.CharField(max_length=64, unique=True, db_index=True)

    payload      = models.JSONField()

    total_km     = models.FloatField(default=0.0)
    total_miles  = models.FloatField(default=0.0)
    total_cost   = models.DecimalField(max_digits=10, decimal_places=2)

    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.start_query} → {self.finish_query}"
