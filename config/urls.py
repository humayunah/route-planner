from django.urls import include, path

urlpatterns = [
    path("api/", include("route_planner.urls")),
]
