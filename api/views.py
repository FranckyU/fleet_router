from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"status": "ok"})


class RouteMapView(APIView):
    """
    GET /api/route_map/

    Placeholder endpoint. For now it returns dummy JSON.
    Later, the external API call + processing will live here.
    """

    def get(self, request):
        dummy = {
            "message": "route map endpoint is alive",
            "source": "dummy",
            "items": [
                {"id": 1, "name": "alpha", "value": 100},
                {"id": 2, "name": "beta", "value": 200},
                {"id": 3, "name": "gamma", "value": 300},
            ],
        }
        return Response(dummy)
