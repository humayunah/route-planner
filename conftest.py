import django
from django.conf import settings


def pytest_configure():
    if not settings.configured:
        settings.configure(
            DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
            INSTALLED_APPS=[
                "django.contrib.contenttypes",
                "django.contrib.auth",
                "rest_framework",
                "route_planner",
            ],
            ROOT_URLCONF="config.urls",
            DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
            NOMINATIM_BASE_URL="https://nominatim.openstreetmap.org",
            OSRM_BASE_URL="https://router.project-osrm.org",
            VEHICLE_RANGE_MILES=500,
            VEHICLE_MPG=10,
            STATION_BUFFER_MILES=25,
            ROUTE_SAMPLE_INTERVAL_MILES=20,
            REST_FRAMEWORK={
                "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
                "UNAUTHENTICATED_USER": None,
            },
        )
    django.setup()
