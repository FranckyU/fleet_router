import hashlib

from django.db import transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from api.exceptions import FuelDataNotLoaded
from api.models import CachedRoute, FuelStation
from api.serializers import RouteMapRequestSerializer
from api.services.route_optimizer import plan_trip


def _route_cache_key(start: str, finish: str) -> str:
    """Deterministic cache key for a (start, finish) pair."""
    raw = f"{start.strip().lower()}|{finish.strip().lower()}".encode()
    return hashlib.sha256(raw).hexdigest()


class HealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"status": "ok"})


class RouteMapView(APIView):
    """
    GET /api/route_map/?start=Chicago,%20IL&finish=Denver,%20CO

    Returns the OSRM route polyline, the optimal fuel stops along it,
    and the total fuel cost for a 500-mile-range vehicle at 10 mpg.

    - Internal distances are computed in kilometers; the 500-mile range
      constraint is preserved as a domain rule.
    - Safe & idempotent: repeat calls yield the same answer.
    - Successful responses are cacheable for a short window.
    """

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        # --- validate query parameters (start, finish) ---
        req = RouteMapRequestSerializer(data=request.query_params)
        req.is_valid(raise_exception=True)

        start  = req.validated_data["start"].strip()
        finish = req.validated_data["finish"].strip()

        # --- fast path: cached plan for the exact same (start, finish) ---
        key    = _route_cache_key(start, finish)
        cached = CachedRoute.objects.filter(cache_key=key).first()
        if cached:
            payload = dict(cached.payload)
            payload["cached"] = True
            response = Response(payload, status=status.HTTP_200_OK)
            response["Cache-Control"] = "public, max-age=300"
            return response

        # --- refuse before burning OSRM/Nominatim if the CSV isn't loaded ---
        if not FuelStation.objects.exists():
            raise FuelDataNotLoaded()

        # --- full planning (RoutePlanError → 502 via exception handler) ---
        result = plan_trip(start, finish)

        # --- persist for future requests with the same (start, finish) ---
        with transaction.atomic():
            CachedRoute.objects.update_or_create(
                cache_key=key,
                defaults={
                    "start_query":  start,
                    "finish_query": finish,
                    "payload":      result,
                    "total_km":     result["total_km"],
                    "total_miles":  result["total_miles"],
                    "total_cost":   result["total_cost"],
                },
            )

        result["cached"] = False
        response = Response(result, status=status.HTTP_200_OK)

        # Let browsers/CDNs reuse the plan for a short window.
        # Tune max-age to match how often your fuel prices refresh.
        response["Cache-Control"] = "public, max-age=300"
        return response


class StationsStatsView(APIView):
    """
    GET /api/stats/

    Reports how many fuel stations are in the DB, and how many of them
    have been geocoded so far. Useful for confirming the CSV load and
    for watching the lazy-geocoding cache fill up across requests.
    """

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        total    = FuelStation.objects.count()
        geocoded = FuelStation.objects.filter(latitude__isnull=False).count()
        return Response({
            "total_stations":    total,
            "geocoded_stations": geocoded,
            "geocoded_pct":      round(100 * geocoded / total, 2) if total else 0.0,
            "data_loaded":       total > 0,
        })


class DebugCacheStatsView(APIView):
    """
    GET /api/debug/cache-stats/

    Exposes the in-process counters from api.services.geocoder so you can
    see the reuse rate of the persistent station-coordinate cache:

    - station_db_hits   : stations whose coords were already in the DB
    - station_db_misses : stations that needed a Nominatim call
    - endpoint_hits     : start/finish strings served from lru_cache
    - endpoint_misses   : start/finish strings that hit Nominatim

    Dev-only. Consider gating with DEBUG or an admin check before shipping.
    """

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        from api.services import geocoder
        return Response(dict(geocoder._CACHE_STATS))

