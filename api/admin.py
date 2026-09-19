from django.contrib import admin

from django.contrib import admin

from api.models import CachedRoute, FuelStation


@admin.register(FuelStation)
class FuelStationAdmin(admin.ModelAdmin):
    list_display  = ("name", "city", "state", "price", "is_geocoded")
    list_filter   = ("state",)
    search_fields = ("name", "city", "opis_id")


@admin.register(CachedRoute)
class CachedRouteAdmin(admin.ModelAdmin):
    list_display  = ("start_query", "finish_query",
                     "total_km", "total_miles", "total_cost", "created_at")
    search_fields = ("start_query", "finish_query")

