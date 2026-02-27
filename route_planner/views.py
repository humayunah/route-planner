from __future__ import annotations

import requests as http_requests
from django.conf import settings
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import FuelStation
from .routing import geocode, get_route
from .serializers import RouteRequestSerializer, RouteResponseSerializer


class RouteView(APIView):
    def post(self, request: Request) -> Response:
        ser = RouteRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        try:
            start_coords = geocode(ser.validated_data["start"])
            finish_coords = geocode(ser.validated_data["finish"])
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except http_requests.RequestException:
            return Response(
                {"error": "Geocoding service unavailable"}, status=status.HTTP_502_BAD_GATEWAY
            )

        try:
            route = get_route(start_coords, finish_coords)
        except (ValueError, http_requests.RequestException) as e:
            return Response({"error": str(e)}, status=status.HTTP_502_BAD_GATEWAY)

        stations_near = FuelStation.objects.near_route(
            route["sampled_points"],
            buffer_miles=settings.STATION_BUFFER_MILES,
        )

        stops, total_cost, total_gallons = FuelStation.objects.find_optimal_stops(
            stations_near,
            route["distance_miles"],
            max_range=settings.VEHICLE_RANGE_MILES,
            mpg=settings.VEHICLE_MPG,
        )

        fuel_stops = [
            {
                "station_name": s["station"].name,
                "address": s["station"].address,
                "city": s["station"].city,
                "state": s["station"].state,
                "latitude": s["station"].latitude,
                "longitude": s["station"].longitude,
                "retail_price": s["station"].retail_price,
                "miles_from_start": s["miles_from_start"],
                "gallons": s["gallons"],
                "cost": s["cost"],
            }
            for s in stops
        ]

        response_data = {
            "start": ser.validated_data["start"],
            "finish": ser.validated_data["finish"],
            "total_distance_miles": route["distance_miles"],
            "total_duration_hours": round(route["duration_seconds"] / 3600, 1),
            "total_fuel_gallons": total_gallons,
            "total_fuel_cost": total_cost,
            "fuel_stops": fuel_stops,
            "route_geometry": route["geometry"],
        }

        out = RouteResponseSerializer(response_data)
        return Response(out.data)
