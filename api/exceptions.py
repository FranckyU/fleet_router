from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler


class FuelDataNotLoaded(Exception):
    """Raised when the FuelStation table is empty (CSV not imported)."""


class RoutePlanError(Exception):
    """Generic planning failure (no station found, OSRM error, etc.)."""


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if isinstance(exc, FuelDataNotLoaded):
        return Response(
            {
                "error": "fuel_data_not_loaded",
                "detail": (
                    "No fuel stations are available in the database. "
                    "Run `python manage.py load_fuel_csv` first."
                ),
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    if isinstance(exc, RoutePlanError):
        return Response(
            {"error": "route_plan_failed", "detail": str(exc)},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    return response
