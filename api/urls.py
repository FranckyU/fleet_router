from django.urls import re_path

from .views import (
    DebugCacheStatsView,
    HealthView,
    RouteMapView,
    StationsStatsView,
)

urlpatterns = [
    re_path(r"^health/?$",              HealthView.as_view(),           name="health"),
    re_path(r"^route_map/?$",           RouteMapView.as_view(),         name="route_map"),
    re_path(r"^stats/?$",               StationsStatsView.as_view(),    name="station-stats"),
    re_path(r"^debug/cache-stats/?$",   DebugCacheStatsView.as_view(),  name="cache-stats"),
]