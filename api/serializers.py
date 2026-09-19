from rest_framework import serializers

from api.models import CachedRoute, FuelStation


class RouteMapRequestSerializer(serializers.Serializer):
    start  = serializers.CharField(max_length=255)
    finish = serializers.CharField(max_length=255)

    def validate(self, attrs):
        if attrs["start"].strip().lower() == attrs["finish"].strip().lower():
            raise serializers.ValidationError(
                "start and finish must be different locations."
            )
        return attrs


class FuelStopSerializer(serializers.Serializer):
    opis_id        = serializers.CharField()
    name           = serializers.CharField()
    city           = serializers.CharField()
    state          = serializers.CharField()
    price          = serializers.FloatField()
    lat            = serializers.FloatField()
    lon            = serializers.FloatField()
    km_from_start  = serializers.FloatField()
    mi_from_start  = serializers.FloatField()
    detour_km      = serializers.FloatField()
    detour_mi      = serializers.FloatField()


class RouteMapResponseSerializer(serializers.Serializer):
    start       = serializers.DictField()
    finish      = serializers.DictField()
    route       = serializers.ListField(
        child=serializers.ListField(child=serializers.FloatField())
    )
    stops       = FuelStopSerializer(many=True)
    total_km    = serializers.FloatField()
    total_miles = serializers.FloatField()
    total_cost  = serializers.FloatField()
    cached      = serializers.BooleanField(required=False)
    assumptions = serializers.DictField(required=False)


class FuelStationSerializer(serializers.ModelSerializer):
    class Meta:
        model  = FuelStation
        fields = "__all__"


class CachedRouteSerializer(serializers.ModelSerializer):
    class Meta:
        model  = CachedRoute
        fields = [
            "id", "start_query", "finish_query",
            "total_km", "total_miles", "total_cost", "created_at",
        ]
