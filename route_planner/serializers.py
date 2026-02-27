from __future__ import annotations

from rest_framework import serializers


class RouteRequestSerializer(serializers.Serializer):
    start = serializers.CharField(help_text="Start location (e.g. 'New York, NY')")
    finish = serializers.CharField(help_text="Finish location (e.g. 'Los Angeles, CA')")


class FuelStopSerializer(serializers.Serializer):
    station_name = serializers.CharField()
    address = serializers.CharField()
    city = serializers.CharField()
    state = serializers.CharField()
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    retail_price = serializers.FloatField()
    miles_from_start = serializers.FloatField()
    gallons = serializers.FloatField()
    cost = serializers.FloatField()


class RouteResponseSerializer(serializers.Serializer):
    start = serializers.CharField()
    finish = serializers.CharField()
    total_distance_miles = serializers.FloatField()
    total_duration_hours = serializers.FloatField()
    total_fuel_gallons = serializers.FloatField()
    total_fuel_cost = serializers.FloatField()
    fuel_stops = FuelStopSerializer(many=True)
    route_geometry = serializers.ListField(
        child=serializers.ListField(child=serializers.FloatField())
    )
