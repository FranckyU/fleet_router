from django.urls import re_path
from .views import HealthView, RouteMapView

urlpatterns = [
    re_path(r"^health/?$", HealthView.as_view(), name="health"),
    re_path(r"^route_map/?$", RouteMapView.as_view(), name="route_map"),
]
